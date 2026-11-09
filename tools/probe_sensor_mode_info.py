"""Replay native OV50H sensor mode-info preparation using firmware tables.

The driver executes in isolated memory with memory functions mocked and a
zeroed HDR-info table; only non-HDR modes are supported. No sensor register,
bus, DSP, clock, or image processing is emulated.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from livephoto_harness import Harness, CONTEXT, ROOT, BASE, image

INPUT, OUTPUT, TIMING = 0x1e7c0e0, 0x1e7c918, 0x3cfdae0


def probe(mode):
    if mode not in (16, 20, 33, 53):
        raise ValueError('Only known non-HDR modes are supported')
    if struct.unpack_from('<I', image(), TIMING - BASE + mode * 36 + 28)[0] != 0:
        raise ValueError('The zeroed HDR table is only valid for non-HDR mode-info paths')
    h = Harness()
    h.uc.mem_map(0x14174000, 0x1000)
    header_table = CONTEXT + 0x4000
    h.uc.mem_write(0x14174dc0, struct.pack('<4Q', INPUT, OUTPUT, TIMING, header_table))
    h.uc.mem_write(CONTEXT, struct.pack('<I', mode))
    destination = CONTEXT + 0x1000

    def memset(uc):
        ptr, value, size = (uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        uc.mem_write(ptr, bytes([value & 255]) * size)
        return 0

    def memcpy(uc):
        dest, src, size = (uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        uc.mem_write(dest, bytes(uc.mem_read(src, size)))
        return 0

    h.mocks = {0x17c0440: memset, 0x17c02c0: memcpy}
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, destination)
    h.run(0x14b5300)
    output = bytes(h.uc.mem_read(destination + 0x70, 32))
    frame_words = list(struct.unpack('<III', h.uc.mem_read(destination + 0x34, 12)))
    rate = struct.unpack_from('<Q', output)[0]
    width, height = struct.unpack_from('<HH', output, 12)
    return dict(mode=mode, native_output_width=width, native_output_height=height,
                native_data_rate=rate, native_bit_depth=output[9],
                native_bayer_code=output[10], native_frame_rate_words=frame_words,
                nominal_fps=(frame_words[1] / frame_words[2] if frame_words[2] else None),
                hdr_info_mocked=True,
                sensor_or_dsp_executed=False)


if __name__ == '__main__':
    results = [probe(i) for i in (16, 20, 33, 53)]
    output = ROOT / 'analysis/motion-resolution-audit/native-sensor-mode-info.json'
    output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
