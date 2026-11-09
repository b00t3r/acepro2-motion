"""Build an offline read-only stat diagnostic, never a flashable package."""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions
from build_gallery_motion_candidate import DEST as SOURCE
from build_motion_candidate import sha
from build_raw_8k_diagnostic_offline import HOOK, LOG_LEVEL, STUB, END, STATE
from probe_guarded_fullsensor import HOOK as CONFIG_HOOK
from livephoto_geometry_patch import branch
from livephoto_harness import BASE,ROOT
from build_usb_name_candidate import unpack_package

OUT=ROOT/'builds/offline-stat-diagnostic'
SOURCE_SHA='9bd908d79770725228e3c96627ee5281e455772c0dcc4b3addaa7b83a1f4e877'
STOP_HOOK=0x306464


def build():
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Unexpected source')
    before=lz4.frame.decompress(unpack_package(source)['parts'][0]['payload'])
    OUT.mkdir(parents=True,exist_ok=True)
    flags=['clang','-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
        '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-fno-jump-tables','-mno-outline-atomics']
    objects=[]
    for name in ('raw_8k_diagnostic_hook.S','fullsensor_marker_hook.S','raw_8k_stat_marker.c','motion_stat_detail.c'):
        obj=OUT/(name+'.o')
        extra=['-mgeneral-regs-only'] if name.endswith('.c') else []
        subprocess.run(flags+extra+['-c',str(ROOT/'tools'/name),'-o',str(obj)],check=True)
        objects.append(obj)
    blobs,symbols,relocs=link_regions([(STUB,END,objects)],{'raw_native_debug':0x276fa4,
        'raw_native_normal':0x276f60,'native_live_continue':CONFIG_HOOK+4,'raw_diag_state':STATE})
    prior=(ROOT/'builds/offline-8k-raw-diagnostic/main_threadx_OFFLINE_ONLY.bin').read_bytes()
    if before[HOOK-BASE:HOOK-BASE+4]!=branch(HOOK,STUB):raise ValueError('Unexpected raw hook')
    if before[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]!=prior[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]:
        raise ValueError('Unexpected marker hook')
    if before[STUB-BASE:0x2552ec0-BASE]!=prior[STUB-BASE:0x2552ec0-BASE]:
        raise ValueError('Unexpected diagnostic code before pool hook')
    if before[LOG_LEVEL-BASE:LOG_LEVEL-BASE+4]!=bytes.fromhex('a0008052'):raise ValueError('Unexpected log level')
    if before[STOP_HOOK-BASE:STOP_HOOK-BASE+4]!=branch(STOP_HOOK,0x2552ec0):raise ValueError('Unexpected stop diagnostic')
    data=bytearray(before)
    data[STUB-BASE:END-BASE]=blobs[0]+bytes(END-STUB-len(blobs[0]))
    data[HOOK-BASE:HOOK-BASE+4]=branch(HOOK,symbols['raw_8k_diagnostic_hook'])
    data[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]=branch(CONFIG_HOOK,symbols['fullsensor_marker_hook'])
    data[STOP_HOOK-BASE:STOP_HOOK-BASE+4]=bytes.fromhex('02778152')
    (OUT/'main_threadx_OFFLINE_ONLY.bin').write_bytes(data)
    report=dict(source_sha256=SOURCE_SHA,bytes=len(blobs[0]),capacity=END-STUB,symbols=symbols,
        status='Offline only; no package or staging.',
        scope='Marker-gated read-only stat of known existing, missing, and invalid-drive paths.',
        limitations=['Marker-gated diagnostic changes the previous pool-diagnostic hook.',
          'Path conversion and filesystem execution are not emulated here.',
          'Code placement, stack and thread behavior must be validated before hardware.'])
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(build(),indent=2))
