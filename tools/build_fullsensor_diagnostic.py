"""Build an offline experimental full-sensor diagnostic; never stage it.

This is not a 20 MP implementation. Before any hardware trial, validate the
full configuration, memory and recovery path and run all relevant tests.
"""
import json
import lz4.frame

from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from probe_guarded_fullsensor import BASE, HOOK, STUB, experimental_image, payload

SOURCE = ROOT / 'builds/offline-highres-memory/Insta360AcePro2_v2.0.51_HighRes-Prerequisite_Memory-Only_Trial-X.bin'
SOURCE_SHA = '519dfd45b163e53259acd6f6c0dc7c061b0c2d1f0d53d80ff47b43c1b4e84846'
OUT = ROOT / 'builds/offline-fullsensor-diagnostic'
DEST = OUT / 'Insta360AcePro2_v2.0.51_FullSensor-Diagnostic_D_NOT-READY.bin'
MARKER = b'Insta360 Ace Pro D'


def patched_image(original):
    result = bytearray(experimental_image(original))
    for offset in USB_OFFSETS:
        if original[offset:offset+18] != b'Insta360 Ace Pro X':
            raise ValueError('Unexpected USB revision marker')
        result[offset:offset+18] = MARKER
    return bytes(result)


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Hardware-tested Trial X package does not match')
    package = unpack_package(source)
    before = lz4.frame.decompress(package['parts'][0]['payload'])
    checked_image = (ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    if before != checked_image:
        raise ValueError('Pinned source image differs from decoded hardware-tested image')
    after = patched_image(before)
    package['parts'][0]['payload'] = edit_frame(package['parts'][0]['payload'], after)
    result = repack(package)
    check = unpack_package(result)
    if len(result) != len(source) or lz4.frame.decompress(check['parts'][0]['payload']) != after:
        raise ValueError('Package roundtrip failed')
    if check['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Unexpected changes to unrelated partitions')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'main_threadx.bin').write_bytes(after)
    DEST.write_bytes(result)
    report = dict(path=str(DEST), sha256=sha(result), source_sha256=SOURCE_SHA,
        status='EXPERIMENTAL: offline candidate only; not approved for hardware testing or staged',
        usb_marker=MARKER.decode(), hook=hex(HOOK), stub=hex(STUB), stub_bytes=len(payload()),
        activation='During Live Photo resource configuration, use capture ID 49 only if resource is 227 and narrow is 1.',
        changes_photo_output_resolution=False, custom_menu_added=False,
        packaging='Existing LRV-based Motion Photo builder retained unchanged; successful output is not established for this profile.',
        unresolved=['DSP work budget for full-sensor format 42 is unknown; Live Photo assigns 0x74000000 bytes.',
                    'Full-sensor template specifies 5 fps sensor input and different streams; live recording and LRV production not verified.',
                    'Still allocation, colour, zoom, full resolution output and PureShot processing not verified.',
                    '2x can be persistent: startup/recovery after an experimental-mode hang is not established.',
                    'The config hook does not prove that enabling 2x triggers reconfiguration.'],
        hardware_tested=False, staged=False)
    (OUT / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
