"""Trial Q: preserve the selected Live Photo bitrate during pre-record setup.

The native branch at 0x28caf0 admits only resource IDs 226, 227 and 228.
Instead of restoring the cached preview bitrate, reload this capture's bitrate.
Keep the native pre-record callback and all other modes unchanged.
"""
import json
import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from build_small_main_candidate import DEST as SOURCE, BASE, BITRATE

SOURCE_SHA = 'af1560cb0ff0cac32dedb9217b76edf2060ad14ad93498611d33ee216c9a54b6'
OUT = ROOT/'builds/offline-gallery-bitrate'
DEST = OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_Small-MP4_Gallery-Fix_Trial-Q.bin'
PATCH = 0x28cb48
ORIGINAL = bytes.fromhex('21444bb9')  # ldr w1,[x1,#0xb44]
REPLACEMENT = bytes.fromhex('412340b9')  # ldr w1,[x26,#0x20]


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Pinned Trial P source changed')
    model = unpack_package(source)
    decoded = bytearray(lz4.frame.decompress(model['parts'][0]['payload']))
    if decoded[PATCH-BASE:PATCH-BASE+4] != ORIGINAL:
        raise ValueError('Unexpected cached bitrate load')
    decoded[PATCH-BASE:PATCH-BASE+4] = REPLACEMENT
    for at in USB_OFFSETS:
        if decoded[at:at+18] != b'Insta360 Ace Pro P':
            raise ValueError('Unexpected USB marker')
        decoded[at:at+18] = b'Insta360 Ace Pro Q'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(decoded))
    candidate = repack(model)
    checked = unpack_package(candidate)
    if len(candidate) != len(source) or lz4.frame.decompress(checked['parts'][0]['payload']) != decoded:
        raise ValueError('Decoded candidate mismatch')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    OUT.mkdir(exist_ok=True)
    DEST.write_bytes(candidate)
    (OUT/'main_threadx.bin').write_bytes(decoded)
    report = dict(path=str(DEST), sha256=sha(candidate), source_sha256=SOURCE_SHA,
                  size=len(candidate), usb_name='Insta360 Ace Pro Q',
                  patch=hex(PATCH), main_video_target_bitrate=BITRATE,
                  status='Offline candidate; validation pending; not staged', hardware_verified=False,
                  scope='Preserve selected bitrate in native Live Photo pre-record setup; keep callback',
                  main_video_stream_disabled=False, main_video_dimensions_changed=False,
                  photo_processing_changed=False, lrv_changed=False,
                  limitations='Hardware test needed after gallery return and after restart; file size varies with scene and vendor metadata.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
