"""Replay native burst RawPiv parameter selection in isolated memory.

The real parameter selector runs unchanged. Configuration reads, formatting
and logging are mocked; no sensor, DSP or storage operations are emulated.
Capture IDs 47/48 use this callback; full-sensor capture ID 49 selects another
callback. Feeding this function template 42 is a counterfactual, not proof of
what that template will do when actually selected.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from livephoto_harness import Harness, CONTEXT, BASE, image
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, ROOT


def probe(format_index=15, narrow=0, factory=2, experimental_full_mode=None,
          special_mode_flag=0):
    if special_mode_flag not in (0, 1):
        raise ValueError('Only Boolean special-mode flags are audited')
    h = Harness()
    start = FORMAT_BASE - 0x20 + format_index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start - BASE:start - BASE + FORMAT_STRIDE])
    h.uc.mem_map(0x12100000, 0x1000)
    h.uc.mem_write(0x12100b2c, struct.pack('<I', special_mode_flag))

    if experimental_full_mode is not None:
        if format_index != 42 or factory != 2 or experimental_full_mode != 53:
            raise ValueError('Experiment only supports the native 5 fps full-raw format')
        # This unscoped in-memory edit is NOT a firmware patch: it answers
        # only whether the selector writes matching mode 53 for both zoom
        # inputs when started from the native 8192x6144 MRAW template. It
        # keeps that template's native IQ value 95. No capture occurs.
        changes = {
            0x287e2c: (0x52800482, 0x528006a2),  # mov w2,#36 -> #53
            0x287e34: (0x52800360, 0x528006a0),  # mov w0,#27 -> #53
            0x287e48: (0x1a820021, 0x52800be1),  # csel w1 -> mov w1,#95
        }
        for addr, (original, replacement) in changes.items():
            if bytes(h.uc.mem_read(addr, 4)) != struct.pack('<I', original):
                raise ValueError('Unexpected native selector at %x' % addr)
            h.uc.mem_write(addr, struct.pack('<I', replacement))

    def state():
        return dict(sensor_mode=struct.unpack('<I', h.uc.mem_read(CONTEXT + 0xc18, 4))[0],
                    iq_mode=struct.unpack('<I', h.uc.mem_read(CONTEXT + 0xc20, 4))[0],
                    capture_sensor_mode=struct.unpack('<I', h.uc.mem_read(CONTEXT + 0x18800, 4))[0],
                    raw_size=list(struct.unpack('<HH', h.uc.mem_read(CONTEXT + 0x187f8, 4))))

    queries = []

    def config(uc):
        key = uc.reg_read(UC_ARM64_REG_X0)
        length = uc.reg_read(UC_ARM64_REG_X2)
        if (key, length) == (0x1c, 8):
            value = struct.pack('<IB3x', 1, narrow)
        elif (key, length) == (1, 12):
            value = struct.pack('<3I', factory, 0, 0)
        else:
            raise ValueError('Unexpected native configuration read: %x/%d' % (key, length))
        queries.append([key, length])
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), value)
        return 0

    h.mocks = {0x2e41a0: config, 0x263900: lambda uc: 0,
               0x2639a0: lambda uc: 0, 0x17d5cc0: lambda uc: 0,
               0x71b880: lambda uc: 0}
    before = state()
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, CONTEXT)
    h.run(0x287a80)
    return dict(format_index=format_index, narrow=narrow, factory=factory,
                before=before, after=state(), config_queries=queries,
                status=h.uc.reg_read(UC_ARM64_REG_X0), hardware_executed=False,
                experimental_full_mode=experimental_full_mode,
                special_mode_flag=special_mode_flag)


if __name__ == '__main__':
    cases = [probe(i, n) for i in (7, 15, 42) for n in (0, 1)]
    report = dict(cases=cases, candidate_created=False, camera_changed=False,
                  native_entry='0x287a80',
                  finding='This burst RawPiv callback overwrites the sensor and capture mode with 36 (wide) or 27 (narrow). Applying it to 8K template data is a counterfactual; capture ID 49 uses a different callback. Raw dimensions are not upgraded by this routine.',
                  limits='Software selection only. Does not prove high-resolution raw capture, colour quality, buffer safety or concurrent recording.')
    folder = ROOT / 'analysis/motion-resolution-audit'
    folder.mkdir(exist_ok=True)
    (folder / 'rawpiv-selection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
