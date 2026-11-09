"""Run the native still-raw pitch setup as an isolated controlled fragment.

This stops before the pitch service: no allocation, DSP or capture is run.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X8, UC_ARM64_REG_X20, UC_ARM64_REG_X23
from livephoto_harness import CONTEXT, Harness, ROOT


def probe(width, compression, alternate_path=0):
    h = Harness()
    cfg = CONTEXT + 0x18000
    h.uc.mem_write(cfg + 0x7ef, bytes([alternate_path]))
    h.uc.mem_write(cfg + 0x7f4, bytes([compression]))
    h.uc.mem_write(cfg + 0x7f8, struct.pack('<H', width))
    h.uc.mem_write(CONTEXT + 0x100, struct.pack('<I', 0))
    h.uc.reg_write(UC_ARM64_REG_X8, cfg)
    h.uc.reg_write(UC_ARM64_REG_X20, CONTEXT + 0x100)
    h.uc.reg_write(UC_ARM64_REG_X23, CONTEXT)
    h.stops = {0x15294a0: 'before_pitch_call', 0x15295d0: 'alternate_path'}
    h.run(0x1529470)
    result = dict(controlled_width=width, controlled_compression=compression,
                  controlled_alternate_path=alternate_path, outcome=h.outcome,
                  hardware_executed=False)
    if h.outcome == 'before_pitch_call':
        result.update(pitch_width=h.uc.reg_read(UC_ARM64_REG_X0),
                      pitch_compression=h.uc.reg_read(UC_ARM64_REG_X1))
    return result


if __name__ == '__main__':
    result = dict(cases=[probe(4096, 0), probe(7680, 3), probe(7680, 0), probe(7680, 3, 1)],
        limitations=['Inputs are hypothetical; the fragment begins after the still-raw enable check.',
          'It stops before pitch calculation and does not perform allocation, DSP setup or image capture.',
          'The 8K still configuration and compression have not been observed on camera.'])
    (ROOT / 'analysis/direct-8k-hardware/still-setup-fragment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
