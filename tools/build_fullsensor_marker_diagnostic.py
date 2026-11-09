"""Build a marker-only camera diagnostic; does not select full-sensor mode."""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions
from build_highres_memory_candidate import DEST as SOURCE
from build_motion_candidate import sha, edit_frame
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_harness import BASE
from livephoto_geometry_patch import branch
from probe_guarded_fullsensor import HOOK, ORIGINAL

SOURCE_SHA = '519dfd45b163e53259acd6f6c0dc7c061b0c2d1f0d53d80ff47b43c1b4e84846'
OUT = ROOT/'builds/offline-marker-diagnostic-l'
DEST = OUT/'Insta360AcePro2_v2.0.51_Marker-Only-Diagnostic_Trial-L.bin'
START, END = 0x2552c40, 0x2552ff0


def patch_image(before):
    OUT.mkdir(exist_ok=True)
    flags = ['clang', '-target', 'aarch64-none-elf', '-Os', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-jump-tables', '-mno-outline-atomics']
    paths = []
    for source in ('fullsensor_marker_hook.S', 'fullsensor_marker_diagnostic.c'):
        out = OUT/(source+'.o')
        extra = [] if source.endswith('.S') else ['-mgeneral-regs-only']
        subprocess.run(flags+extra+['-c', str(ROOT/'tools'/source), '-o', str(out)], check=True)
        paths.append(out)
    blobs, symbols, _ = link_regions([(START, END, paths)], {'native_live_continue': HOOK+4})
    body = blobs[0]
    after = bytearray(before)
    if after[HOOK-BASE:HOOK-BASE+4] != ORIGINAL or any(after[START-BASE:START-BASE+len(body)]):
        raise ValueError('Unexpected code site or occupied gap')
    if symbols['fullsensor_marker_hook'] != START:
        raise ValueError('Unexpected hook entry')
    after[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, START)
    after[START-BASE:START-BASE+len(body)] = body
    for at in USB_OFFSETS:
        if before[at:at+18] != b'Insta360 Ace Pro X':
            raise ValueError('Unexpected source marker')
        after[at:at+18] = b'Insta360 Ace Pro L'
    return bytes(after), symbols, len(body)


def main():
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA: raise ValueError('Source package hash mismatch')
    package = unpack_package(source)
    before = lz4.frame.decompress(package['parts'][0]['payload'])
    if before != (ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes():
        raise ValueError('Source differs from hardware-tested image')
    after, symbols, size = patch_image(before)
    package['parts'][0]['payload'] = edit_frame(package['parts'][0]['payload'], after)
    result = repack(package)
    check = unpack_package(result)
    if len(result) != len(source) or lz4.frame.decompress(check['parts'][0]['payload']) != after:
        raise ValueError('Package roundtrip failed')
    if check['parts'][1:] != unpack_package(source)['parts'][1:]:
        raise ValueError('Other partitions changed')
    DEST.write_bytes(result)
    (OUT/'main_threadx.bin').write_bytes(after)
    report = dict(path=str(DEST), sha256=sha(result), source_sha256=SOURCE_SHA,
        marker='Insta360 Ace Pro L', code_bytes=size,
        status='Offline marker-only diagnostic; tests and hardware verification required; not staged',
        camera_mode_changed=False, fullsensor_enabled=False,
        notes=['During 4:3 Live Photo configuration at either zoom, tests for C:\\FULLSENSOR.ENABLE and logs marker status 0 missing/error, 1 found/closed, 2 close failure.',
               'The new synchronous card read and log call occur in configuration code; their startup timing, thread safety, stack capacity and card-removal behavior are unverified.',
               'Larger full-sensor mode, its memory budget, stream output and recovery are not tested.'])
    (OUT/'build_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
