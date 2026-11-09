"""Inspect the existing selection transition for an unsupported resolution.

Runs original ARM64 code up to its lookup-failure branch, with config/storage
and notification calls simulated. This does not change firmware or a camera.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from livephoto_harness import Harness, ROOT


def probe(requested=8, initial=2):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    state = {0x2e: struct.pack('<I', initial),
             0x12: struct.pack('<5I', 1, 0, 12, 17, 0),
             0x1c: struct.pack('<IBHB', 1, 1, 100, 0)}
    writes = []

    def get(uc):
        key, dest, size = (uc.reg_read(reg) for reg in
                           (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        data = state.get(key)
        if data is None or len(data) != size:
            raise ValueError('Unexpected configuration read %x/%d' % (key, size))
        uc.mem_write(dest, data)
        return 0

    def put(uc):
        key, src, size = (uc.reg_read(reg) for reg in
                          (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        if key not in state or size != len(state[key]):
            raise ValueError('Unexpected configuration write %x/%d' % (key, size))
        state[key] = bytes(uc.mem_read(src, size))
        writes.append(dict(key=hex(key), data_hex=state[key].hex()))
        return 0

    h.mocks = {0x2e41a0: get, 0x2e4380: get, 0x2e4ae0: put,
               0x373a60: lambda uc: 0, 0x36c160: lambda uc: 0,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0,
               0x363340: lambda uc: 0, 0x341fc0: lambda uc: 0,
               0x365da0: lambda uc: 0}
    h.stops[0x36e9dc] = 'resource_lookup_failed'
    h.stops[0x36ec30] = 'resource_lookup_succeeded'
    h.uc.reg_write(UC_ARM64_REG_X0, requested)
    h.run(0x36e800, max_instructions=100000)
    return dict(initial_resolution=initial, requested_resolution=requested,
                resolution_after_write=struct.unpack('<I', state[0x2e])[0],
                narrow_after_write=state[0x1c][4], outcome=h.outcome,
                writes=writes, storage_and_notifications_mocked=True,
                camera_changed=False)


if __name__ == '__main__':
    results = [probe(8), probe(3)]
    assert results[0]['outcome'] == 'resource_lookup_failed'
    assert results[0]['resolution_after_write'] == 8
    assert results[1]['outcome'] == 'resource_lookup_succeeded'
    path = ROOT / 'analysis/motion-resolution-audit/custom-transition-probe.json'
    path.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
