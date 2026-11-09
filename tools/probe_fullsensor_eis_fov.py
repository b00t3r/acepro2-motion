"""Run native main/sub FOV lookup over the two original template layouts.

No ISP, sensor or hardware is emulated. Config fields are controlled inputs;
actual execution can modify the copied template before this lookup.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE
from livephoto_harness import BASE, CONTEXT, Harness, ROOT, image


def run(index, capture_id):
    h = Harness((ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    start = FORMAT_BASE - 0x20 + index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start-BASE:start-BASE+FORMAT_STRIDE])
    h.uc.mem_write(CONTEXT+0x18d02, struct.pack('<HHH',227,capture_id,capture_id))
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, CONTEXT+0x1f000)
    h.uc.reg_write(UC_ARM64_REG_X2, CONTEXT+0x1f008)
    h.mocks = {0x2639a0:lambda uc:0, 0x71b880:lambda uc:0}
    h.run(0x287340)
    main, sub = struct.unpack('<QQ',h.uc.mem_read(CONTEXT+0x1f000,16))
    signed=lambda p: struct.unpack('<b',h.uc.mem_read(CONTEXT+p,1))[0]
    word=lambda ptr: struct.unpack('<I',h.uc.mem_read(ptr+0xe8,4))[0] if ptr else None
    descriptors=[]
    for f in range(2):
        at = start-BASE+0x441c+f*0x104
        descriptors.append(dict(index=f, source_kind=hex(struct.unpack_from('<I',image(),at+0xa8)[0]),
            main_lookup_type=hex(struct.unpack_from('<I',image(),at+0xc8)[0]),
            sub_lookup_flags=hex(struct.unpack_from('<I',image(),at+0xd8)[0]),
            iq_word=hex(struct.unpack_from('<I',image(),at+0xe8)[0])))
    return dict(format_index=index,capture_id=capture_id, main_fov_index=signed(0x18d4d),
                sub_fov_index=signed(0x18d55),main_pointer=hex(main),sub_pointer=hex(sub),
                main_iq_word=hex(word(main)) if main else None,
                sub_iq_word=hex(word(sub)) if sub else None,
                descriptors=descriptors, initialized_fov_override_mocked=False)


def run_eis_setup(index, capture_id, feature_enabled):
    """Run real EIS setup and real FOV lookup with an explicit feature mock."""
    h = Harness((ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    start = FORMAT_BASE - 0x20 + index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start-BASE:start-BASE+FORMAT_STRIDE])
    h.uc.mem_map(0x12100000, 0x1000)
    h.uc.mem_write(CONTEXT+0x18d02, struct.pack('<HHH',227,capture_id,capture_id))
    h.uc.mem_write(CONTEXT+0x18d0a,b'\x01')
    h.uc.mem_write(CONTEXT+0x18d0c,struct.pack('<H',1))
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    queries=[]
    def config(uc):
        key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
        if size > 32: raise ValueError('Unexpected config read length')
        queries.append([key,size])
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1),bytes(size))
        return 0
    h.mocks = {0x2639a0:lambda uc:0, 0x71b880:lambda uc:0,
               0x1198200:lambda uc:int(feature_enabled), 0x293ec0:lambda uc:0,
               0x2e4380:config, 0x2e41a0:config}
    from unicorn import UC_HOOK_CODE
    trace = []
    def remember(uc, address, size, unused):
        trace.append(address)
        if len(trace)>20: del trace[0]
    h.uc.hook_add(UC_HOOK_CODE, remember)
    try:
        h.run(0x294a20)
    except Exception as exc:
        from unicorn.arm64_const import UC_ARM64_REG_PC
        raise RuntimeError('EIS setup fault at %s for format %d: %s; recent instructions %s' %
                           (hex(h.uc.reg_read(UC_ARM64_REG_PC)), index, exc,
                            [hex(v) for v in trace])) from exc
    signed=lambda p: struct.unpack('<b',h.uc.mem_read(CONTEXT+p,1))[0]
    return dict(format_index=index,capture_id=capture_id,feature_mock=feature_enabled,
                main_fov_index=signed(0x18d4d),sub_fov_index=signed(0x18d55),
                live_eis_byte=h.uc.mem_read(CONTEXT+0x18d0a,1)[0],
                fov0_iq=hex(struct.unpack('<I',h.uc.mem_read(CONTEXT+0x441c+0xe8,4))[0]),
                fov1_iq=hex(struct.unpack('<I',h.uc.mem_read(CONTEXT+0x4520+0xe8,4))[0]),
                native_lookup_and_setup_executed=True, controlled_zero_config_reads=queries)


def main():
    result=dict(cases=[run(16,30),run(42,49)],
        eis_setup_cases=[run_eis_setup(i,c,f) for i,c in ((16,30),(42,49)) for f in (False,True)],hardware_tested=False,
        limit='Template-copy lookup only; runtime configuration, stabilization, sensor and DSP remain unverified.')
    out=ROOT/'analysis/trial-h-bootloop/eis-fov-lookup.json'
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
