"""Trial N: keep Live Photo zoom out of PureShot's raw-format decision."""
import json
import struct
from pathlib import Path

import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import branch, instruction

SOURCE = ROOT/'builds/offline-motion-photo/Insta360AcePro2_v2.0.51_LivePhoto-2x_Extra-MotionPhoto_Trial-M.bin'
SOURCE_SHA = '040fd19f232e3ab05b25bd4c03fa8fbd0c2c028c30a5d15b45aa637910d35d22'
OUT = ROOT/'builds/offline-pureshot-colour'
DEST = OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_PureShot-Colour-Test_Trial-N.bin'
BASE = 0x50000
HOOK = 0x755cd8
STUB = 0x50e80
LIVE_FLAG = 0x1262e904


def patch_bytes():
    # Replay the local narrow-byte load. Preserve x9, SP, LR and NZCV. Only
    # the local format decision sees zero during Live Photo; zoom state and
    # geometry are untouched. Branch back without changing the link register.
    page = (((LIVE_FLAG & ~4095) - ((STUB+8) & ~4095)) >> 12) & 0x1fffff
    return b''.join([
        bytes.fromhex('e0334439'),                  # ldrb w0,[sp,#0x10c]
        instruction(0xf81f0fe9),                    # str x9,[sp,#-16]!
        instruction(0x90000009 | (page & 3)<<29 | (page >> 2)<<5),
        instruction(0xb9400000 | ((LIVE_FLAG & 4095)//4)<<10 | 9<<5 | 9),
        instruction(0x34000009 | 2<<5),             # cbz w9,restore
        instruction(0x52800000),                    # mov w0,#0
        instruction(0xf84107e9),                    # ldr x9,[sp],#16
        branch(STUB+28, HOOK+4),
    ])


def main():
    OUT.mkdir(exist_ok=True)
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Known-good Trial M source changed')
    model = unpack_package(source)
    original = lz4.frame.decompress(model['parts'][0]['payload'])
    after = bytearray(original)
    payload = patch_bytes()
    if after[HOOK-BASE:HOOK-BASE+4] != bytes.fromhex('e0334439'):
        raise ValueError('Unexpected format-selection hook instruction')
    if any(after[STUB-BASE:STUB-BASE+len(payload)]):
        raise ValueError('Colour stub would overwrite existing code')
    after[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
    after[STUB-BASE:STUB-BASE+len(payload)] = payload
    for offset in USB_OFFSETS:
        if after[offset:offset+18] != b'Insta360 Ace Pro M':
            raise ValueError('Unexpected baseline USB marker')
        after[offset:offset+18] = b'Insta360 Ace Pro N'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(after))
    candidate = repack(model)
    checked = unpack_package(candidate)
    if len(candidate) != len(source) or lz4.frame.decompress(checked['parts'][0]['payload']) != after:
        raise ValueError('Packaged image verification failed')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    DEST.write_bytes(candidate)
    (OUT/'main_threadx.bin').write_bytes(after)
    report = dict(path=str(DEST), sha256=sha(candidate), source_sha256=SOURCE_SHA,
                  size=len(candidate), usb_name='Insta360 Ace Pro N',
                  status='Offline candidate; tests pending; not staged',
                  hardware_verified=False, hook=hex(HOOK), stub=hex(STUB),
                  scope='PureShot raw-format decision only; green JPG fault remains unresolved',
                  save_speed_changes=False)
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
