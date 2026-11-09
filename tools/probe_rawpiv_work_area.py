"""Run the native RawPiv work-area initializer with controlled inputs.

The caller supplies memory; this routine does not allocate it. Logging is mocked.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1
from livephoto_harness import Harness, ROOT

STATE = 0x1281ff88


def probe(base, size):
    h = Harness()
    h.uc.mem_map(0x1281f000, 0x4000)
    h.uc.reg_write(UC_ARM64_REG_X0, base)
    h.uc.reg_write(UC_ARM64_REG_X1, size)
    h.mocks = {0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.run(0x76c4e0)
    start, end, cursor, stored_size = struct.unpack('<QQQI', bytes(h.uc.mem_read(STATE + 0x1a88, 28)))
    return dict(controlled_base=base, controlled_size=size, start=start, end=end,
                cursor=cursor, stored_size=stored_size, hardware_executed=False)


if __name__ == '__main__':
    result = dict(cases=[probe(0x80000000, 31457280), probe(0x80000000, 82944000)],
        limitations=['The input address and size are controlled; no memory is allocated or accessed there.',
          'Logging services are mocked. The production caller and available memory have not been established.',
          'This does not run raw capture or decompression.'])
    (ROOT / 'analysis/direct-8k-hardware/rawpiv-work-area.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
