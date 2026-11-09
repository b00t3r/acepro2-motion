"""Trial S: force the Live Photo CapMode-27 fallback to the normal 36 path.

The native code already restricts this change to a value of 27 at 0x282424.
It normally chooses 9 for one flag combination and 36 otherwise.  Keeping
the comparison/guard and replacing only the conditional select makes the
experiment narrow: ordinary modes and CapMode values are untouched.
"""
import json
from pathlib import Path

import lz4.frame

from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack

SOURCE = ROOT / 'builds/offline-fast-copy/Insta360AcePro2_v2.0.51_LivePhoto-2x_Small-MP4_64KB-Copy_Trial-R.bin'
SOURCE_SHA = '4e25037dba980f025e1bc3a244a3ae2ddaa0a5f567f262c9e0d33bb0adf239c6'
OUT = ROOT / 'builds/offline-capmode36'
DEST = OUT / 'Insta360AcePro2_v2.0.51_LivePhoto-2x_CapMode36_Trial-S.bin'
BASE = 0x50000
PATCH = 0x282454
ORIGINAL = bytes.fromhex('0000841a')  # csel w0,w0,w4,eq
REPLACEMENT = bytes.fromhex('1f2003d5')  # nop; retain w0=36


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Pinned Trial R source changed')
    model = unpack_package(source)
    decoded = bytearray(lz4.frame.decompress(model['parts'][0]['payload']))
    off = PATCH - BASE
    if decoded[off:off + 4] != ORIGINAL:
        raise ValueError('Unexpected CapMode select instruction')
    decoded[off:off + 4] = REPLACEMENT
    for at in USB_OFFSETS:
        if decoded[at:at + 18] != b'Insta360 Ace Pro R':
            raise ValueError('Unexpected USB marker')
        decoded[at:at + 18] = b'Insta360 Ace Pro S'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(decoded))
    candidate = repack(model)
    checked = unpack_package(candidate)
    if len(candidate) != len(source) or lz4.frame.decompress(checked['parts'][0]['payload']) != decoded:
        raise ValueError('Decoded candidate mismatch')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    OUT.mkdir(exist_ok=True)
    DEST.write_bytes(candidate)
    (OUT / 'main_threadx.bin').write_bytes(decoded)
    report = dict(path=str(DEST), sha256=sha(candidate), source_sha256=SOURCE_SHA,
                  usb_name='Insta360 Ace Pro S', patch=hex(PATCH),
                  original=ORIGINAL.hex(), replacement=REPLACEMENT.hex(),
                  status='Offline candidate; not staged', hardware_verified=False,
                  scope='Guarded CapMode 27 fallback only; preserves 64KB copy, small MP4, Motion Photo and colour patches',
                  limitation='Hardware test required; CapMode 27 is not independently sufficient to prove the green fault.')
    (OUT / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
