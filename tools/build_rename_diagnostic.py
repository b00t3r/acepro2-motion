"""Build offline diagnostic; not staged. Only test files can be renamed."""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions
from build_motion_candidate import sha,edit_frame
from build_stat_diagnostic_offline import SOURCE,SOURCE_SHA,HOOK,LOG_LEVEL,STUB,END,STOP_HOOK
from build_usb_name_candidate import unpack_package,repack,USB_OFFSETS
from livephoto_harness import BASE,ROOT
from livephoto_geometry_patch import branch
from probe_guarded_fullsensor import HOOK as CONFIG_HOOK

OUT=ROOT/'builds/offline-rename-diagnostic'
PAD, PAD_END=0x50e30,0x50e80

def build(kind='rename'):
    if kind not in ('rename','delete'): raise ValueError('Unknown diagnostic')
    out=OUT if kind=='rename' else ROOT/'builds/offline-delete-diagnostic'
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Unexpected source firmware')
    model=unpack_package(source)
    before=lz4.frame.decompress(model['parts'][0]['payload'])
    previous=(ROOT/'builds/offline-8k-raw-diagnostic/main_threadx_OFFLINE_ONLY.bin').read_bytes()
    if before[HOOK-BASE:HOOK-BASE+4]!=branch(HOOK,STUB):raise ValueError('Raw hook mismatch')
    if before[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]!=previous[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]:raise ValueError('Config hook mismatch')
    if before[STUB-BASE:0x2552ec0-BASE]!=previous[STUB-BASE:0x2552ec0-BASE]:raise ValueError('Diagnostic area mismatch')
    if before[STOP_HOOK-BASE:STOP_HOOK-BASE+4]!=branch(STOP_HOOK,0x2552ec0):raise ValueError('Stop hook mismatch')
    if before[LOG_LEVEL-BASE:LOG_LEVEL-BASE+4]!=bytes.fromhex('a0008052'):raise ValueError('Log level mismatch')
    if any(before[PAD-BASE:PAD_END-BASE]):raise ValueError('Motion padding occupied')
    if any(before[0x2552fe0-BASE:0x2552ff0-BASE]):raise ValueError('Latch area occupied')
    out.mkdir(parents=True,exist_ok=True)
    flags=['clang','-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
      '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
      '-fno-jump-tables','-mno-outline-atomics']
    objs=[]
    for name in ('fullsensor_marker_hook.S',kind+'_diagnostic_compact.c','rename_diagnostic_strings.c'):
        obj=out/(name+'.o'); extra=['-mgeneral-regs-only'] if name.endswith('.c') else []
        subprocess.run(flags+extra+['-c',str(ROOT/'tools'/name),'-o',str(obj)],check=True);objs.append(obj)
    blobs,symbols,_=link_regions([(STUB,END,objs[:2]),(PAD,PAD_END,objs[2:])],{'native_live_continue':CONFIG_HOOK+4})
    after=bytearray(before)
    after[STUB-BASE:END-BASE]=blobs[0]+bytes(END-STUB-len(blobs[0]))
    after[PAD-BASE:PAD_END-BASE]=blobs[1]+bytes(PAD_END-PAD-len(blobs[1]))
    after[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]=branch(CONFIG_HOOK,symbols['fullsensor_marker_hook'])
    after[HOOK-BASE:HOOK-BASE+4]=bytes.fromhex('40021037')
    after[LOG_LEVEL-BASE:LOG_LEVEL-BASE+4]=bytes.fromhex('c0008052')
    after[STOP_HOOK-BASE:STOP_HOOK-BASE+4]=bytes.fromhex('02778152')
    for off in USB_OFFSETS:
        if after[off:off+18]!=b'Insta360 Ace Pro t':raise ValueError('USB mismatch')
        after[off:off+18]=b'Insta360 Ace Pro v' if kind=='rename' else b'Insta360 Ace Pro w'
    (out/'main_threadx_OFFLINE_ONLY.bin').write_bytes(after)
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    result=repack(model);check=unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(check['parts'][0]['payload'])!=after:raise ValueError('Roundtrip mismatch')
    if check['parts'][1:]!=unpack_package(source)['parts'][1:]:raise ValueError('Other partitions changed')
    dest=out/('Insta360AcePro2_Rename-Diagnostic_Trial-V3.bin' if kind=='rename' else 'Insta360AcePro2_Delete-Diagnostic_Trial-W3.bin');dest.write_bytes(result)
    report=dict(source_sha256=SOURCE_SHA,sha256=sha(result),package=str(dest),symbols=symbols,
       code_bytes=len(blobs[0]),code_capacity=END-STUB,strings_bytes=len(blobs[1]),strings_capacity=PAD_END-PAD,
       status='Offline candidate; not staged or hardware-tested',usb_name='Insta360 Ace Pro '+('v' if kind=='rename' else 'w'))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':print(json.dumps(build(),indent=2))
