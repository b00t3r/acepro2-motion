"""Trial R: 64 KiB synchronous Motion Photo copies; all capture paths retain Q."""
import json
import subprocess
import lz4.frame
from build_motion_candidate import BASE, CAVE, HOOK, link_payload, edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from build_gallery_bitrate_candidate import DEST as SOURCE

SOURCE_SHA='814e4a727f72def6d19f43e6cb4a0614449d1d4c61321712db21a0d9eea1b5e3'
OUT=ROOT/'builds/offline-fast-copy'
DEST=OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_Small-MP4_64KB-Copy_Trial-R.bin'
PAYLOAD_END=0x50e80  # Existing PureShot colour stub starts here: never overwrite.
COPY_BYTES=65536


def main():
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA:raise ValueError('Pinned Q source changed')
    OUT.mkdir(exist_ok=True)
    common=['clang','-target','aarch64-none-elf']
    subprocess.run(common+['-Os','-ffreestanding','-fno-builtin','-fno-stack-protector',
        '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-jump-tables',
        '-mgeneral-regs-only','-DMOTION_COPY_BYTES=65536','-c',str(ROOT/'tools/motion_photo_payload.c'),
        '-o',str(OUT/'payload.o')],check=True)
    subprocess.run(common+['-c',str(ROOT/'tools/motion_photo_entry.S'),'-o',str(OUT/'entry.o')],check=True)
    payload,symbols,relocations=link_payload([OUT/'entry.o',OUT/'payload.o'])
    if CAVE+len(payload)>PAYLOAD_END or symbols['motion_hook']!=CAVE:
        raise ValueError('Fast payload would overlap existing colour fix or move hook')
    model=unpack_package(source)
    before=lz4.frame.decompress(model['parts'][0]['payload'])
    old=(ROOT/'builds/offline-motion-photo/payload.bin').read_bytes()
    if before[CAVE-BASE:CAVE-BASE+len(old)]!=old or any(before[CAVE-BASE+len(old):PAYLOAD_END-BASE]):
        raise ValueError('Unexpected source payload or occupied padding')
    after=bytearray(before)
    after[CAVE-BASE:PAYLOAD_END-BASE]=payload+bytes(PAYLOAD_END-CAVE-len(payload))
    for at in USB_OFFSETS:
        if after[at:at+18]!=b'Insta360 Ace Pro Q':raise ValueError('Unexpected USB marker')
        after[at:at+18]=b'Insta360 Ace Pro R'
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    candidate=repack(model);checked=unpack_package(candidate)
    if len(candidate)!=len(source) or lz4.frame.decompress(checked['parts'][0]['payload'])!=after:
        raise ValueError('Candidate package mismatch')
    if checked['parts'][1:]!=unpack_package(source)['parts'][1:]:raise ValueError('Other partitions changed')
    DEST.write_bytes(candidate);(OUT/'main_threadx.bin').write_bytes(after);(OUT/'payload.bin').write_bytes(payload)
    report=dict(path=str(DEST),sha256=sha(candidate),size=len(candidate),source_sha256=SOURCE_SHA,
        usb_name='Insta360 Ace Pro R',copy_bytes=COPY_BYTES,allocation_bytes=COPY_BYTES+1024,
        payload_bytes=len(payload),symbols=symbols,relocations=relocations,
        status='Offline candidate; validation pending; not staged',hardware_verified=False,
        background_saving=False,photo_processing_changed=False,lrv_changed=False,
        timing='Use native Save img / Free metadata buffer / capture-idle log markers; post-metadata interval includes scheduling.',
        limitations='64 KiB buffer reduces copy calls; actual time gain unverified. Allocation failure skips extra Motion Photo while preserving originals.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('symbols','relocations')},indent=2))


if __name__=='__main__':main()
