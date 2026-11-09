"""Trial T: guard the actual narrow sensor-mode assignment for Live Photo.

Source is Trial R: rejected Trial S's unrelated CSEL change is not included.
At 0x282410 native code tests the requested narrow flag. Only that branch
reaches 0x2826a8, which changes modes 3, 9, or 36 to 27 and persists it.
Replay that assignment with 36 only when the native Live Photo flag is set.
"""
import json
import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import branch, instruction
from build_capmode36_candidate import SOURCE, SOURCE_SHA, BASE

OUT = ROOT / 'builds/offline-live-capmode'
DEST = OUT / 'Insta360AcePro2_v2.0.51_LivePhoto-2x_Green-Test_Trial-T.bin'
HOOK = 0x2826a8
STUB = 0x50ec0
LIVE_FLAG = 0x1262e904


def patch_bytes():
    page = (((LIVE_FLAG & ~4095) - ((STUB + 8) & ~4095)) >> 12) & 0x1fffff
    return b''.join([
        instruction(0x52800360),                 # original mov w0,#27
        instruction(0xf81f0fe9),                 # save x9, aligned stack
        instruction(0x90000009 | (page & 3)<<29 | (page >> 2)<<5),
        instruction(0xb9400000 | ((LIVE_FLAG & 4095)//4)<<10 | 9<<5 | 9),
        instruction(0x34000009 | 2<<5),          # cbz w9,restore
        instruction(0x52800480),                 # Live Photo: mov w0,#36
        instruction(0xf84107e9),                 # restore x9 and stack
        branch(STUB + 28, HOOK + 4),
    ])


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Pinned Trial R source changed')
    model = unpack_package(source)
    decoded = bytearray(lz4.frame.decompress(model['parts'][0]['payload']))
    payload = patch_bytes()
    if decoded[HOOK-BASE:HOOK-BASE+4] != bytes.fromhex('60038052'):
        raise ValueError('Unexpected actual mode assignment')
    if decoded[0x282454-BASE:0x282458-BASE] != bytes.fromhex('0000841a'):
        raise ValueError('Rejected S change present')
    if any(decoded[STUB-BASE:STUB-BASE+len(payload)]):
        raise ValueError('Stub area occupied')
    decoded[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
    decoded[STUB-BASE:STUB-BASE+len(payload)] = payload
    for at in USB_OFFSETS:
        if decoded[at:at+18] != b'Insta360 Ace Pro R':
            raise ValueError('Unexpected source marker')
        decoded[at:at+18] = b'Insta360 Ace Pro T'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(decoded))
    result = repack(model)
    checked = unpack_package(result)
    if len(result) != len(source) or lz4.frame.decompress(checked['parts'][0]['payload']) != decoded:
        raise ValueError('Package roundtrip failed')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    OUT.mkdir(exist_ok=True)
    DEST.write_bytes(result)
    (OUT/'main_threadx.bin').write_bytes(decoded)
    report = dict(path=str(DEST), sha256=sha(result), source_sha256=SOURCE_SHA,
                  hook=hex(HOOK), stub=hex(STUB), usb_name='Insta360 Ace Pro T',
                  status='Offline only; native execution tests pending; not staged',
                  hardware_verified=False, rejected_s_patch_included=False,
                  scope='Native narrow assignment: keep mode 36 when Live Photo enabled; ordinary narrow assignments retain 27',
                  limitation='Tests cannot emulate the sensor/ISP; hardware needed to confirm colour and zoom.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
