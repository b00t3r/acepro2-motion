"""Trace the actual template callback to its delegated callback boundary.

The actual 0x295ea0 callback executes against a template copied to isolated
memory. Frame metadata selection and its delegated callback are mocked, so
this is not a complete profile or hardware test.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE
from livephoto_harness import BASE, CONTEXT, Harness, ROOT, image
from probe_capture_template_callback import probe as callback_for


def probe(index, capture_id, through_delegate=False, narrow=0, overrides=None):
    descriptor = callback_for(capture_id)
    if descriptor['callback'] != '0x295ea0':
        raise ValueError('Expected ordinary profile callback for this experiment')
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    start = FORMAT_BASE - 0x20 + index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start-BASE:start-BASE+FORMAT_STRIDE])
    for offset, data in (overrides or {}).items():
        h.uc.mem_write(CONTEXT + offset, data)
    if struct.unpack('<H', h.uc.mem_read(CONTEXT + 0x18cfa, 2))[0] != capture_id:
        raise ValueError('Capture ID and template do not match')

    def frame_lookup(uc):
        for reg in (UC_ARM64_REG_X1, UC_ARM64_REG_X2):
            uc.mem_write(uc.reg_read(reg), bytes(8))
        return 0

    observed = []
    def delegated(uc):
        observed.append(dict(sensor_mode=struct.unpack('<I', uc.mem_read(CONTEXT+0xc18, 4))[0],
                             capture_mode=struct.unpack('<I', uc.mem_read(CONTEXT+0x18800, 4))[0],
                             raw_size=list(struct.unpack('<HH', uc.mem_read(CONTEXT+0x187f8, 4)))))
        return 0

    h.mocks = {0x263900: lambda uc: 0, 0x17d5cc0: lambda uc: 0,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0,
               0x287340: frame_lookup}
    queries = []
    if through_delegate:
        def config(uc):
            key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
            if (key, size) not in ((0x2d, 4), (0x1c, 8)):
                raise ValueError('Unexpected controlled config read %x/%d' % (key, size))
            queries.append([key, size])
            data = struct.pack('<IBHB', 1, narrow, 100, 0) if key == 0x1c else bytes(size)
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), data)
            return 0
        h.mocks.update({0x7745e0: lambda uc: 1, 0x294a20: lambda uc: 0,
                        0x28a520: lambda uc: 0, 0x2e7040: lambda uc: 0,
                        0x1786ac0: lambda uc: 0, 0x28ff60: lambda uc: 0,
                        0x2e41a0: config, 0x2e4380: config})
        h.stops[0x296020] = 'delegate_returned'
    else:
        h.mocks[0x294f60] = delegated
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, int(descriptor['descriptor'], 16))
    h.run(0x295ea0, max_instructions=100000)
    if through_delegate:
        delegated_status = h.uc.reg_read(UC_ARM64_REG_X0) & 0xffffffff
        observed.append(dict(sensor_mode=struct.unpack('<I', h.uc.mem_read(CONTEXT+0xc18, 4))[0],
                             capture_mode=struct.unpack('<I', h.uc.mem_read(CONTEXT+0x18800, 4))[0],
                             raw_size=list(struct.unpack('<HH', h.uc.mem_read(CONTEXT+0x187f8, 4)))))
    if len(observed) != 1:
        raise ValueError('Expected a single delegated callback')
    return dict(template=index, capture_id=capture_id, callback=descriptor['callback'],
                observed_at_delegated_callback=observed[0],
                frame_lookup_mocked=True, delegated_callback_mocked=not through_delegate,
                controlled_config_reads=queries, narrow=narrow, outcome=h.outcome,
                experimental_overrides=sorted(hex(x) for x in (overrides or {})),
                delegated_status=delegated_status if through_delegate else None,
                complete_configuration_validated=False, hardware_executed=False)


if __name__ == '__main__':
    results = [probe(16, 30), probe(42, 49)] + [probe(42, 49, True, n) for n in (0, 1)]
    output = ROOT / 'analysis/motion-resolution-audit/fullsensor-actual-callback.json'
    output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
