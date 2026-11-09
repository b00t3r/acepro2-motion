"""Offline full-sensor diagnostic with removable marker; not a 20 MP feature."""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions
from build_fullsensor_marker_diagnostic import DEST as SOURCE, START, END
from build_motion_candidate import sha, edit_frame
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_harness import BASE
from livephoto_geometry_patch import branch
from probe_guarded_fullsensor import HOOK

SOURCE_SHA = '53916802f24664705310862e7bd4ebeb9b29400d669200dd1514401e614c8a0b'
OUT = ROOT/'builds/offline-marked-fullsensor'
DEST = OUT/'Insta360AcePro2_v2.0.51_Marked-FullSensor-Diagnostic_Trial-H.bin'


def patched_image(before):
    OUT.mkdir(exist_ok=True)
    flags = ['clang', '-target', 'aarch64-none-elf', '-Os', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-jump-tables', '-mno-outline-atomics']
    paths = []
    for source in ('fullsensor_marker_hook.S', 'fullsensor_marker_active.c'):
        obj = OUT/(source+'.o')
        extra = [] if source.endswith('.S') else ['-mgeneral-regs-only']
        subprocess.run(flags+extra+['-c', str(ROOT/'tools'/source), '-o', str(obj)], check=True)
        paths.append(obj)
    blobs, symbols, _ = link_regions([(START, END, paths)], {'native_live_continue': HOOK+4})
    body = blobs[0]
    if symbols['fullsensor_marker_hook'] != START or before[HOOK-BASE:HOOK-BASE+4] != branch(HOOK, START):
        raise ValueError('Unexpected source hook')
    source_image = (ROOT/'builds/offline-marker-diagnostic-l/main_threadx.bin').read_bytes()
    if before != source_image:
        raise ValueError('Source differs from hardware-tested Trial L image')
    result = bytearray(before)
    result[START-BASE:END-BASE] = body + bytes(END-START-len(body))
    for at in USB_OFFSETS:
        if before[at:at+18] != b'Insta360 Ace Pro L': raise ValueError('Unexpected USB name')
        result[at:at+18] = b'Insta360 Ace Pro H'
    return bytes(result), len(body)


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA: raise ValueError('Source package hash mismatch')
    package = unpack_package(source)
    before = lz4.frame.decompress(package['parts'][0]['payload'])
    after, size = patched_image(before)
    package['parts'][0]['payload'] = edit_frame(package['parts'][0]['payload'], after)
    result = repack(package)
    check = unpack_package(result)
    if len(result) != len(source) or lz4.frame.decompress(check['parts'][0]['payload']) != after:
        raise ValueError('Package roundtrip failed')
    if check['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Unrelated partitions changed')
    DEST.write_bytes(result)
    (OUT/'main_threadx.bin').write_bytes(after)
    report = dict(path=str(DEST), sha256=sha(result), source_sha256=SOURCE_SHA,
        marker='Insta360 Ace Pro H', code_bytes=size,
        status='Experimental offline candidate; full-sensor hardware operation not verified',
        scope='Only 4:3 Live Photo with C:\\FULLSENSOR.ENABLE present and readable switches capture ID 30 to 49; missing marker retains Trial L behavior.',
        higher_jpeg_resolution_implemented=False, menu_implemented=False,
        limits=['The full-sensor profile has 5 fps sensor timing and a different stream layout.',
                'DSP memory requirement, output dimensions, colours and Google Motion Photo video remain unverified.',
                'Marker removal was tested in normal mode, but recovery from a full-sensor hang was not.',
                'A marker-present boot may activate this mode when Live Photo is persisted; the bootloader recovery path is unverified.'])
    (OUT/'build_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
