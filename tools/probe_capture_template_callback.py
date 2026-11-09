"""Resolve actual native capture-template callbacks in the emulator.

Only the dispatch lookup runs; callbacks, camera, sensor and DSP do not.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0
from livephoto_harness import Harness, ROOT


def probe(capture_id):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    h.mocks = {0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.uc.reg_write(UC_ARM64_REG_X0, capture_id)
    h.run(0x288800)
    pointer = h.uc.reg_read(UC_ARM64_REG_X0)
    if not pointer:
        return dict(capture_id=capture_id, descriptor=None)
    name = bytes(h.uc.mem_read(pointer, 64)).split(b'\0')[0].decode('ascii')
    key = struct.unpack('<H', h.uc.mem_read(pointer + 0x40, 2))[0]
    callback = struct.unpack('<Q', h.uc.mem_read(pointer + 0x48, 8))[0]
    if key != capture_id:
        raise ValueError('Native callback lookup returned a different ID')
    return dict(capture_id=capture_id, descriptor=hex(pointer), name=name,
                callback=hex(callback), callback_executed=False, hardware_executed=False)


if __name__ == '__main__':
    results = [probe(i) for i in (30, 31, 47, 48, 49, 50)]
    output = ROOT / 'analysis/motion-resolution-audit/capture-template-callbacks.json'
    output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
