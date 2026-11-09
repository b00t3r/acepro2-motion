"""Trial X: memory preflight for higher-resolution 4:3 Live Photos.

This prerequisite does NOT change photo resolution or sensor/ISP settings.
Only 4:3 Live Photo's video bitstream reservation is reduced to ~256 MiB.
Never stages an update. Camera validation is required before a larger readout.
"""
import json
import struct
import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import branch, instruction

SOURCE = ROOT / 'builds/offline-background-save/Insta360AcePro2_v2.0.51_LivePhoto-2x_MotionPhoto_Background-Save_Trial-W.bin'
SOURCE_SHA = '86b60ce8192e4789f3fb5d8a80a0cd0fa595c46564938d222d873263fec76fb1'
OUT = ROOT / 'builds/offline-highres-memory'
DEST = OUT / 'Insta360AcePro2_v2.0.51_HighRes-Prerequisite_Memory-Only_Trial-X.bin'
BASE, HOOK, STUB = 0x50000, 0x1524f1c, 0x2552c00
ORIGINAL = instruction(0x321137e2)
CTX = 0x100b5e60  # Native SvcResCfg_Get at 0x15c3420.
RES = CTX + 0x18d02
LIVE = CTX + 0x18d0a


def payload():
    page = (((RES & ~4095) - (STUB + 8 & ~4095)) >> 12) & 0x1fffff
    adrp = 0x90000009 | (page & 3) << 29 | (page >> 2) << 5
    def bne(at, target):
        return instruction(0x54000001 | (((target-at)//4) & 0x7ffff) << 5)
    return b''.join([
        instruction(0xa9bf2be9),  # stp x9,x10,[sp,#-16]!
        instruction(0xd53b420a),  # preserve NZCV, as original MOV leaves flags alone
        instruction(adrp),
        instruction(0x79400002 | ((RES & 4095)//2) << 10 | 9 << 5),
        instruction(0x7100005f | 227 << 10),  # only dedicated 4:3 Live resource
        bne(STUB + 20, STUB + 44),
        instruction(0x39400002 | (LIVE & 4095) << 10 | 9 << 5),
        instruction(0x7100045f),  # current context's Live marker == 1
        bne(STUB + 32, STUB + 44),
        instruction(0x321133e2),  # ~256 MiB cap
        branch(STUB + 40, STUB + 48),
        ORIGINAL,                # all other contexts retain native ~512 MiB cap
        instruction(0xd51b420a),
        instruction(0xa8c12be9),
        branch(STUB + 56, HOOK + 4),
    ])


def patched_image(before):
    after = bytearray(before)
    body = payload()
    if after[HOOK-BASE:HOOK-BASE+4] != ORIGINAL:
        raise ValueError('Unexpected allocator cap instruction')
    if any(after[STUB-BASE:STUB-BASE+len(body)]):
        raise ValueError('Memory stub overlaps occupied Trial W code')
    # Trial W's worker ends before this gap; its persistent root is 0x2552ff0.
    if STUB + len(body) >= 0x2552ff0:
        raise ValueError('Memory stub overlaps worker state')
    if before[0x15c3420-BASE:0x15c342c-BASE] != bytes.fromhex('805707d000803991c0035fd6'):
        raise ValueError('Unexpected native resource context getter')
    after[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
    after[STUB-BASE:STUB-BASE+len(body)] = body
    for at in USB_OFFSETS:
        if before[at:at+18] != b'Insta360 Ace Pro W':
            raise ValueError('Unexpected installed revision marker')
        after[at:at+18] = b'Insta360 Ace Pro X'
    return bytes(after)


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Verified Trial W source changed')
    package = unpack_package(source)
    before = lz4.frame.decompress(package['parts'][0]['payload'])
    after = patched_image(before)
    OUT.mkdir(exist_ok=True)
    (OUT / 'main_threadx.bin').write_bytes(after)
    package['parts'][0]['payload'] = edit_frame(package['parts'][0]['payload'], after)
    result = repack(package)
    check = unpack_package(result)
    if len(result) != len(source) or lz4.frame.decompress(check['parts'][0]['payload']) != after:
        raise ValueError('Update roundtrip failed')
    if check['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Unrelated partitions changed')
    DEST.write_bytes(result)
    report = dict(path=str(DEST), sha256=sha(result), source_sha256=SOURCE_SHA,
        status='Offline memory-only prerequisite; tests pending; not staged',
        usb_name='Insta360 Ace Pro X', higher_resolution_enabled=False,
        hardware_verified=False, hook=hex(HOOK), stub=hex(STUB), stub_bytes=len(payload()),
        scope='4:3 Live Photo resource 227 with context Live byte 1 only; leave all capture/ISP/stream settings unchanged.',
        working_features_retained=['2x zoom', 'colour fix', 'small real main MP4', 'LRV Motion Photo video', 'background packaging'],
        expected_original_cap=0x1fff8000, expected_live_4x3_cap=0x0fff8000,
        expected_usable_live_4x3_video_buffer=0x0fff0000,
        limitations=['Does not yet increase photo resolution.',
                    'Larger sensor-streaming buffers and full-resolution DSP/ISP settings remain unvalidated.',
                    'Recording, JPEG sharing, pre-recording and gallery require hardware checks.'],
        hardware_test=['Verify USB marker X after installation.',
                       'Take one 1x and one 2x PureShot Live Photo in 4:3; check still colours and motion in the camera gallery.',
                       'Take a short ordinary video to check that its allocation remains native.',
                       'Export LOG once and reconnect; inspect allocations and every capture before attempting a larger sensor readout.'])
    (OUT / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
