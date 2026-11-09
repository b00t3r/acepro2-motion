"""Trial P: record a small compatibility MP4 from the start of Live Photo.

The main video stream remains active at its native dimensions and frame rate.
Only its target bitrate changes. Still images, LRV, Motion Photo packaging,
capture timing and ordinary video configuration retain Trial N's bytes.
"""
import json
import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import instruction

SOURCE = ROOT/'builds/offline-pureshot-colour/Insta360AcePro2_v2.0.51_LivePhoto-2x_PureShot-Colour-Test_Trial-N.bin'
SOURCE_SHA = 'f8f95352ce7dd0fa58c572552b07378f0a955c8a23571b613ce111941e35382f'
OUT = ROOT/'builds/offline-small-main'
DEST = OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_Small-Playback-MP4_Trial-P.bin'
BASE = 0x50000
BITRATE = 2*1024*1024
PATCHES = (0x4015cc, 0x4015e4, 0x401714)
ORIGINAL = bytes.fromhex('002c0c53')  # lsl w0,w0,#20
REPLACEMENT = instruction(0x52a00000 | (BITRATE >> 16)<<5)  # mov w0,#0x200000


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Verified Trial N source changed')
    model = unpack_package(source)
    before = lz4.frame.decompress(model['parts'][0]['payload'])
    after = bytearray(before)
    for address in PATCHES:
        at = address-BASE
        if after[at:at+4] != ORIGINAL:
            raise ValueError('Unexpected bitrate instruction at %x' % address)
        after[at:at+4] = REPLACEMENT
    for at in USB_OFFSETS:
        if after[at:at+18] != b'Insta360 Ace Pro N':
            raise ValueError('Unexpected USB marker')
        after[at:at+18] = b'Insta360 Ace Pro P'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(after))
    candidate = repack(model)
    checked = unpack_package(candidate)
    if len(candidate) != len(source) or lz4.frame.decompress(checked['parts'][0]['payload']) != after:
        raise ValueError('Packaged image mismatch')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    OUT.mkdir(exist_ok=True)
    DEST.write_bytes(candidate)
    (OUT/'main_threadx.bin').write_bytes(after)
    report = dict(path=str(DEST), sha256=sha(candidate), source_sha256=SOURCE_SHA,
                  size=len(candidate), usb_name='Insta360 Ace Pro P',
                  status='Offline candidate; tests pending; not staged', hardware_verified=False,
                  main_video_target_bitrate=BITRATE, main_video_stream_disabled=False,
                  main_video_dimensions_changed=False, lrv_changed=False, photo_processing_changed=False,
                  scope='Small low-quality compatibility MP4 recorded directly; originals are not deleted or replaced',
                  patches=[hex(a) for a in PATCHES],
                  limitations='Encoder target is not a file-size guarantee; main MP4 quality is intentionally reduced. Hardware validation pending.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
