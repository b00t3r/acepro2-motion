"""Place optimized gallery-compatible builder in the tested slot, offline only."""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions
from build_fast_copy_candidate import PAYLOAD_END
from build_motion_candidate import BASE, CAVE, sha
from build_record_pool_diagnostic_candidate import DEST as SOURCE
from build_usb_name_candidate import ROOT, unpack_package

OUT = ROOT/'builds/offline-gallery-motion'
SOURCE_SHA = 'fe451767b0e2ed76ff4da37dbf9074fb7c2dcf19f53c296744536d3303672b02'


def build():
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Unexpected source firmware')
    before=lz4.frame.decompress(unpack_package(source)['parts'][0]['payload'])
    baseline=(ROOT/'builds/offline-background-save/main_threadx.bin').read_bytes()
    if before[CAVE-BASE:PAYLOAD_END-BASE] != baseline[CAVE-BASE:PAYLOAD_END-BASE]:
        raise ValueError('Unexpected existing Motion Photo payload')
    OUT.mkdir(parents=True,exist_ok=True)
    flags=['-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
           '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics']
    entry=OUT/'entry.o';payload=OUT/'payload-optimized.o'
    subprocess.run(['clang',*flags,'-DMOTION_BACKGROUND_WORKER','-c',
                    str(ROOT/'tools/motion_photo_entry.S'),'-o',str(entry)],check=True)
    subprocess.run(['clang',*flags,'-DMOTION_CAPTURED_TIMESTAMP','-DMOTION_COPY_BYTES=65536',
                    '-DMOTION_GALLERY_TRAILER','-c',str(ROOT/'tools/motion_photo_payload.c'),
                    '-o',str(payload)],check=True)
    blobs,symbols,relocs=link_regions([(CAVE,PAYLOAD_END,[entry,payload])],{'motion_submit':0x2552480})
    if symbols['motion_hook']!=CAVE or symbols['motion_save_captured']!=0x502bc:
        raise ValueError('Existing hook/worker call target moved')
    data=bytearray(before);blob=blobs[0]
    data[CAVE-BASE:PAYLOAD_END-BASE]=blob+bytes(PAYLOAD_END-CAVE-len(blob))
    (OUT/'main_threadx_OFFLINE_ONLY.bin').write_bytes(data)
    report=dict(source_sha256=SOURCE_SHA,payload_bytes=len(blob),capacity=PAYLOAD_END-CAVE,
        motion_hook=hex(symbols['motion_hook']),save_entry=hex(symbols['motion_save_captured']),
        status='Offline image only; originals retained; no camera update.',
        limitations=['Existing worker and original media are unchanged; automatic cleanup is not implemented.',
          'Optimization changes generated code and requires isolated tests; no scheduler or storage hardware is emulated.',
          'No flashable package or camera staging.'])
    (OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(build(),indent=2))
