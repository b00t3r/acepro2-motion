#!/usr/bin/env python3
"""Replay the stock ISP table selector with the inputs in the 962/963 logs.

This executes ARM64 selection code, not the ISP or its pixel processing.
No firmware or camera files are changed.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X20
from livephoto_harness import Harness, CONTEXT, BASE, image

TABLE = 0x349eb28
# The real registration at 0x118f614 passes 0x26d rows. A shorter scan
# reproduces the live/zoom cases but misses the ordinary full-res profiles.
TABLE_COUNT = 621
PARAMS = 0x3c19d58
FIELDS = {
    'sensor': 0, 'main_mode': 4, 'sub_mode': 8, 'resolution': 0xc,
    'fps': 0x10, 'factory': 0x14, 'still_type': 0x1c,
    'sharpen': 0x20, 'eis': 0x24, 'colour': 0x28, 'recording': 0x2c,
    'narrow': 0x34, 'aiisp': 0x38, 'hdr': 0x4c, 'vpu': 0x50,
    'low_power': 0x54, 'face': 0x5c, 'log_restore': 0x60,
    'lens': 0x68, 'flash': 0x6c,
}


def replay(recording, narrow=1, face=1, image_data=None, still_type=0,
           live_flag=0, sub_mode=17, main_mode=1, sensor=8,
           resolution=3, hdr=1, fps=0, allow_unmatched=False, lens=1):
    h = Harness(image_data)
    values = dict(sensor=sensor, main_mode=main_mode, sub_mode=sub_mode, resolution=resolution, fps=fps,
                  factory=2, still_type=still_type, sharpen=1, eis=1, colour=1,
                  recording=recording, narrow=narrow, aiisp=0, hdr=hdr,
                  vpu=0, low_power=0, face=face, log_restore=0, lens=lens, flash=0)
    h.uc.mem_write(PARAMS, bytes(0x70))
    for name, value in values.items():
        h.uc.mem_write(PARAMS + FIELDS[name], struct.pack('<I', value))
    h.uc.reg_write(UC_ARM64_REG_X0, 0)
    h.uc.mem_write(0x1262e904, struct.pack('<I', live_flag))
    h.uc.reg_write(UC_ARM64_REG_X1, TABLE)
    h.uc.reg_write(UC_ARM64_REG_X2, TABLE_COUNT)
    h.uc.reg_write(UC_ARM64_REG_X3, CONTEXT)
    h.mocks[0x1226114] = lambda uc: 0
    h.stops[0x11c2024] = 'matched'
    h.stops[0x11c21a4] = 'fallback'
    h.run(0x11c1e40, max_instructions=200000)
    if h.outcome != 'matched':
        if allow_unmatched and h.outcome == 'fallback':
            return dict(inputs=values, row=None, table=None, root=None,
                        outcome='No match among the %d registered rows for these supplied inputs; stopped before native fallback.' % TABLE_COUNT)
        raise RuntimeError('Observed inputs did not select an expected stock row')
    root = struct.unpack('<Q', h.uc.mem_read(CONTEXT, 8))[0]
    name_ptr = struct.unpack('<Q', h.uc.mem_read(root, 8))[0]
    name = bytes(h.uc.mem_read(name_ptr, 100)).split(b'\0')[0].decode()
    return dict(inputs=values, row=h.uc.reg_read(UC_ARM64_REG_X20),
                table=name, root=hex(root))


def filter_headers():
    # Group-7 pointers in the actual live-still and zoom-main subtables,
    # for ordinary and face-optimized tuning respectively.
    entries = {'live_default': 0x39db420, 'live_face': 0x39dc1a8,
               'zoom_default': 0x39dce58, 'zoom_face': 0x39ddbe0}
    data = image()
    out = {}
    for name, slot in entries.items():
        ptr = struct.unpack_from('<Q', data, slot - BASE)[0]
        header = struct.unpack_from('<3I40i', data, ptr - BASE)
        out[name] = dict(pointer=hex(ptr), parameter_id=header[2],
                         first_40_values=sorted(set(header[3:])))
    return out


if __name__ == '__main__':
    print(json.dumps(dict(before_first=replay(1), after_first=replay(0),
                          filter_headers=filter_headers(),
                          limit='Selection reproduced; ISP causality still needs hardware validation.'), indent=2))
