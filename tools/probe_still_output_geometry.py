"""Run the native still DSP output-geometry fragment in isolated memory.

Only the control structure written by the native instructions is observed.
The DSP, scaler, pixels, JPEG encoder, allocation and hardware are not run.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X27
from livephoto_harness import Harness, CONTEXT, ROOT


def probe(raw_width=8192, raw_height=6144, output_width=5120,
          output_height=3840, scale=2):
    if any(not 0 < n <= 65535 for n in (raw_width, raw_height, output_width, output_height)):
        raise ValueError('Geometry must fit native unsigned halfwords')
    if not 0 <= scale <= 255:
        raise ValueError('Scale control must fit one byte')
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    cfg = CONTEXT + 0x18000
    h.uc.mem_write(cfg + 0x808, struct.pack('<HHH', 0, raw_width, raw_height))
    h.uc.mem_write(cfg + 0x80e, bytes([scale]))
    h.uc.mem_write(cfg + 0x810, struct.pack('<HH', output_width, output_height))
    h.uc.reg_write(UC_ARM64_REG_X27, cfg)
    h.uc.reg_write(UC_ARM64_REG_X0, 1)
    h.stops[0x3268ac] = 'before_following_native_call'
    h.run(0x326858)
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    pairs = [list(struct.unpack('<II', h.uc.mem_read(sp + offset, 8)))
             for offset in (0x180, 0x188, 0x1d0, 0x1d8)]
    return dict(raw_size=[raw_width, raw_height], configured_output=[output_width, output_height],
                scale_control=scale, native_structure_pairs=pairs,
                outcome=h.outcome, hardware_executed=False,
                pixels_or_encoder_validated=False)


if __name__ == '__main__':
    cases = [probe(scale=0), probe(scale=2),
             probe(8192, 6144, 8192, 4608, 2),
             probe(4096, 3072, 4096, 2304, 2)]
    output = ROOT / 'analysis/motion-resolution-audit/still-output-geometry.json'
    output.write_text(json.dumps(cases, indent=2) + '\n')
    print(json.dumps(cases, indent=2))
