"""Build Trial W on colour-fixed U, with background Motion Photo packaging.

The shutter's original capture-readiness tests are untouched. New waits are
at storage consumers, not by clearing a native saving/buffer-ownership flag.
"""
import json
import subprocess
import lz4.frame
from build_background_prototype import link_regions, WORKER_BASE, WORKER_END
from build_motion_candidate import BASE, CAVE, edit_frame, sha
from build_fast_copy_candidate import PAYLOAD_END
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack
from livephoto_geometry_patch import branch, instruction

SOURCE = ROOT/'builds/offline-live-isp/Insta360AcePro2_v2.0.51_LivePhoto-2x_ISP-Selection-Test_Trial-U.bin'
SOURCE_SHA = '3bcb12eb9fabd0c8f902a489d1f30d2f3a530904e4419f7b1b13dccd0f298060'
OUT = ROOT/'builds/offline-background-save'
DEST = OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_MotionPhoto_Background-Save_Trial-W.bin'
EXTERNALS = dict(native_gallery_continue=0x879f24, native_usb_continue=0x38d1e4,
                 native_format_continue=0x7fc084, native_delete_continue=0x26ab04,
                 native_delete_invalid=0x26ab18, native_poweroff_step=0x3a0e20,
                 native_capture_busy=0x32da80)
HOOKS = [(0x879f20, 'fd7ba9a9', 'motion_gallery_guard', False),
         (0x38d1e0, 'fd7bb6a9', 'motion_usb_guard', False),
         (0x7fc080, 'fd7bb6a9', 'motion_format_guard', False),
         (0x26ab00, 'c00000b4', 'motion_delete_guard', False),
         (0x3a1670, 'ecfdff97', 'motion_poweroff_guard', True),
         (0x3a134c, 'cd31fe97', 'motion_shutdown_busy_guard', True),
         (0x3a1440, '9031fe97', 'motion_shutdown_busy_guard', True),
         (0x3a14e0, '6831fe97', 'motion_shutdown_busy_guard', True)]


def hook_branch(at, target, link=False):
    value=int.from_bytes(branch(at,target),'little')
    return instruction(value | (0x80000000 if link else 0))


def main():
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Pinned verified U changed')
    model=unpack_package(source)
    before=lz4.frame.decompress(model['parts'][0]['payload'])
    OUT.mkdir(exist_ok=True)
    flags=['clang','-target','aarch64-none-elf','-Os','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
           '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics']
    for name, ext, defines in [('motion_photo_entry','.S',['-DMOTION_BACKGROUND_WORKER']),
                             ('motion_photo_payload','.c',['-DMOTION_CAPTURED_TIMESTAMP','-DMOTION_COPY_BYTES=65536']),
                             ('motion_worker_port','.c',[]), ('motion_worker_guards','.S',[])]:
        subprocess.run(flags+defines+['-c',str(ROOT/'tools'/(name+ext)),'-o',str(OUT/(name+'.o'))],check=True)
    groups=[(CAVE,PAYLOAD_END,[OUT/'motion_photo_entry.o',OUT/'motion_photo_payload.o']),
            (WORKER_BASE,WORKER_END,[OUT/'motion_worker_port.o',OUT/'motion_worker_guards.o'])]
    blobs,symbols,relocs=link_regions(groups,EXTERNALS)
    after=bytearray(before)
    if any(before[WORKER_BASE-BASE:0x2553000-BASE]): raise ValueError('Worker region occupied')
    for (base,end,_),blob in zip(groups,blobs): after[base-BASE:end-BASE]=blob+bytes(end-base-len(blob))
    if symbols['motion_hook']!=CAVE: raise ValueError('Existing producer hook moved')
    for at,expected,name,link in HOOKS:
        if before[at-BASE:at-BASE+4]!=bytes.fromhex(expected): raise ValueError('Unexpected storage hook at '+hex(at))
        after[at-BASE:at-BASE+4]=hook_branch(at,symbols[name],link)
    for at in USB_OFFSETS:
        if before[at:at+18]!=b'Insta360 Ace Pro U': raise ValueError('Unexpected USB marker')
        after[at:at+18]=b'Insta360 Ace Pro W'
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    result=repack(model);checked=unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(checked['parts'][0]['payload'])!=after:
        raise ValueError('Package roundtrip failed')
    if checked['parts'][1:]!=unpack_package(source)['parts'][1:]: raise ValueError('Other partitions changed')
    DEST.write_bytes(result);(OUT/'main_threadx.bin').write_bytes(after)
    report=dict(path=str(DEST),sha256=sha(result),source_sha256=SOURCE_SHA,
                usb_name='Insta360 Ace Pro W',status='Offline candidate; validation pending; not staged',
                hardware_verified=False,storage_barriers_hooked=True,
                hooks=[dict(address=hex(a),symbol=n,link=l) for a,e,n,l in HOOKS],
                regions=[dict(start=hex(g[0]),end=hex(g[1]),bytes=len(b)) for g,b in zip(groups,blobs)],
                symbols=symbols,relocations=relocs,
                scope='Motion Photo file packaging only; retains U colour fix and native shutter readiness',
                limitations='Native scheduler and storage concurrency require hardware validation. No earlier raw/PureShot stage is made asynchronous.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('symbols','relocations')},indent=2))


if __name__=='__main__': main()
