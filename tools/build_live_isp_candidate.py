"""Trial U: use native Live Photo ISP selection after recording stops.

Based on the installed T to isolate the ISP change from the sensor-mode test.
Only the selector's local narrow input is masked, for OV50H photo mode 17
with Live Photo enabled. Actual zoom, capture flags and geometry stay intact.
"""
import json
import lz4.frame
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import branch, instruction

SOURCE = ROOT / 'builds/offline-live-capmode/Insta360AcePro2_v2.0.51_LivePhoto-2x_Green-Test_Trial-T.bin'
SOURCE_SHA = 'df3c29b2e3152578e2f4de29eaa5c02743c8a823b5fae4904e39e96c6f94d18b'
OUT = ROOT / 'builds/offline-live-isp'
DEST = OUT / 'Insta360AcePro2_v2.0.51_LivePhoto-2x_ISP-Selection-Test_Trial-U.bin'
BASE, HOOK, STUB, LIVE_FLAG = 0x50000, 0x11c1ebc, 0x50f00, 0x1262e904
ORIGINAL = bytes.fromhex('d0c64629')


def patch_bytes():
    restore = STUB + 60
    def bne(at):
        return instruction(0x54000001 | (((restore-at)//4) & 0x7ffff) << 5)
    page = (((LIVE_FLAG & ~4095) - ((STUB+44) & ~4095)) >> 12) & 0x1fffff
    return b''.join([
        ORIGINAL,                                # ldp w16,w17,[x22,#0x34]
        instruction(0xa9bf2be9),                  # save x9,x10
        instruction(0xd53b420a),                  # save NZCV in x10
        instruction(0x7100049f), bne(STUB+16),    # main mode == photo (1)
        instruction(0x710044bf), bne(STUB+24),    # actual submode == Live Photo (17)
        instruction(0x7100207f), bne(STUB+32),    # OV50H module == 8
        instruction(0x7100061f), bne(STUB+40),    # narrow input == 1
        instruction(0x90000009 | (page & 3)<<29 | (page >> 2)<<5),
        instruction(0xb9400000 | ((LIVE_FLAG & 4095)//4)<<10 | 9<<5 | 9),
        instruction(0x34000009 | 2<<5),          # disabled -> restore
        instruction(0x52800010),                 # local match input only: w16=0
        instruction(0xd51b420a),                  # restore NZCV
        instruction(0xa8c12be9),                  # restore x9,x10,SP
        branch(STUB+68, HOOK+4),
    ])


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Pinned installed Trial T changed')
    model = unpack_package(source)
    decoded = bytearray(lz4.frame.decompress(model['parts'][0]['payload']))
    payload = patch_bytes()
    if decoded[HOOK-BASE:HOOK-BASE+4] != ORIGINAL:
        raise ValueError('Unexpected native ISP selector instruction')
    if any(decoded[STUB-BASE:STUB-BASE+len(payload)]) or STUB+len(payload)>0x51000:
        raise ValueError('ISP stub space occupied or overlaps startup vectors')
    decoded[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
    decoded[STUB-BASE:STUB-BASE+len(payload)] = payload
    for at in USB_OFFSETS:
        if decoded[at:at+18] != b'Insta360 Ace Pro T':
            raise ValueError('Unexpected USB marker')
        decoded[at:at+18] = b'Insta360 Ace Pro U'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(decoded))
    result = repack(model)
    checked = unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(checked['parts'][0]['payload'])!=decoded:
        raise ValueError('Package roundtrip failed')
    if checked['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    OUT.mkdir(exist_ok=True)
    DEST.write_bytes(result)
    (OUT/'main_threadx.bin').write_bytes(decoded)
    report = dict(path=str(DEST),sha256=sha(result),source_sha256=SOURCE_SHA,
                  usb_name='Insta360 Ace Pro U',hook=hex(HOOK),stub=hex(STUB),
                  status='Offline candidate; tests pending; not staged',
                  hardware_verified=False,
                  scope='Live Photo native ISP table matching only; actual narrow flag remains 1',
                  limitation='Software execution verifies table selection, not resulting ISP colour.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
