"""Link an OFFLINE worker image for emulator tests; deliberately no update BIN.

Storage transition call sites are not wired. This tool never repacks a camera
update and must not be used to stage its raw decoded image.
"""
import json
import struct
import subprocess
from pathlib import Path
import lz4.frame
from build_motion_candidate import BASE,CAVE,read_elf,sha
from build_fast_copy_candidate import DEST as SOURCE,PAYLOAD_END
from build_usb_name_candidate import ROOT,unpack_package

SOURCE_SHA='4e25037dba980f025e1bc3a244a3ae2ddaa0a5f567f262c9e0d33bb0adf239c6'
WORKER_BASE=0x2552020
WORKER_END=0x2552ff0
OUT=ROOT/'builds/offline-background-prototype'


def link_regions(groups, extra_symbols=None):
    symbols={'memcpy':0x17c0140,'memset':0x17d3e00}
    symbols.update(extra_symbols or {})
    units=[];buffers={};locations={};relocations=[]
    for region,(base,end,paths) in enumerate(groups):
        buf=bytearray();buffers[region]=buf
        for path in paths:
            sections,syms=read_elf(path);unit=len(units)
            units.append((region,sections,syms))
            for si,sec in enumerate(sections):
                if not sec['flags']&2 or not sec['size']:continue
                if sec['type']!=1 or sec['flags']&1:raise ValueError('Unexpected mutable/BSS section')
                buf.extend(bytes(-(base+len(buf))%max(sec['align'],1)))
                locations[unit,si]=(region,base+len(buf))
                buf.extend(sec['data'])
            for sym in syms:
                if sym['section'] and sym['name'] and not sym['name'].startswith('$'):
                    where=locations.get((unit,sym['section']))
                    if where:symbols[sym['name']]=where[1]+sym['value']
        if base+len(buf)>end:raise ValueError('Prototype exceeds audited region: %x + %d > %x'%(base,len(buf),end))
    for unit,(region,sections,syms) in enumerate(units):
        base=groups[region][0];buf=buffers[region]
        for sec in sections:
            if sec['type']!=4 or (unit,sec['info']) not in locations:continue
            for p in range(0,sec['size'],24):
                offset,info,addend=struct.unpack_from('<QQq',sec['data'],p);sym=syms[info>>32]
                target=(locations[unit,sym['section']][1]+sym['value'] if sym['section'] else symbols[sym['name']])+addend
                place=locations[unit,sec['info']][1]+offset;at=place-base
                kind=info&0xffffffff;w=struct.unpack_from('<I',buf,at)[0]
                if kind==257:  # R_AARCH64_ABS64, for read-only function pointers
                    if at<0 or at+8>len(buf):raise ValueError('Absolute relocation outside region')
                    struct.pack_into('<Q',buf,at,target)
                    relocations.append({'kind':kind,'place':hex(place),'target':hex(target),'symbol':sym['name']})
                    continue
                if kind in (282,283):
                    delta=target-place
                    if delta%4 or not -(1<<27)<=delta<1<<27:raise ValueError('Branch range')
                    w=(w&0xfc000000)|((delta>>2)&0x3ffffff)
                elif kind==275:
                    imm=((target&~4095)-(place&~4095))>>12
                    if not -(1<<20)<=imm<1<<20:raise ValueError('ADRP range')
                    w=(w&~0x60ffffe0)|((imm&3)<<29)|(((imm>>2)&0x7ffff)<<5)
                elif kind==277:w=(w&~0x003ffc00)|((target&4095)<<10)
                else:raise ValueError('Unsupported relocation %d'%kind)
                struct.pack_into('<I',buf,at,w)
                relocations.append({'kind':kind,'place':hex(place),'target':hex(target),'symbol':sym['name']})
    return [bytes(buffers[r]) for r in range(len(groups))],symbols,relocations


def main():
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA:raise ValueError('Pinned Trial R changed')
    OUT.mkdir(exist_ok=True)
    flags=['clang','-target','aarch64-none-elf','-Os','-ffreestanding','-fno-builtin',
        '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics']
    for name,defines in [('motion_photo_entry',['-DMOTION_BACKGROUND_WORKER']),
                         ('motion_photo_payload',['-DMOTION_CAPTURED_TIMESTAMP','-DMOTION_COPY_BYTES=65536']),
                         ('motion_worker_port',[])]:
        ext='.S' if name.endswith('entry') else '.c'
        subprocess.run(flags+defines+['-c',str(ROOT/'tools'/(name+ext)),'-o',str(OUT/(name+'.o'))],check=True)
    groups=[(CAVE,PAYLOAD_END,[OUT/'motion_photo_entry.o',OUT/'motion_photo_payload.o']),
            (WORKER_BASE,WORKER_END,[OUT/'motion_worker_port.o'])]
    blobs,symbols,relocations=link_regions(groups)
    before=lz4.frame.decompress(unpack_package(source)['parts'][0]['payload']);after=bytearray(before)
    if any(before[WORKER_BASE-BASE:0x2553000-BASE]):raise ValueError('Alignment gap not empty')
    for (base,end,_),blob in zip(groups,blobs):after[base-BASE:end-BASE]=blob+bytes(end-base-len(blob))
    if symbols['motion_hook']!=CAVE:raise ValueError('Hook moved')
    (OUT/'main_threadx_OFFLINE_ONLY.bin').write_bytes(after)
    report=dict(status='Offline ARM integration prototype; NOT a camera update',
        source_sha256=SOURCE_SHA,decoded_image_sha256=sha(after),
        regions=[{'start':hex(g[0]),'end':hex(g[1]),'bytes':len(b)} for g,b in zip(groups,blobs)],
        symbols=symbols,relocations=relocations,root_slot=hex(WORKER_END),
        storage_barriers_hooked=False,hardware_ready=False,update_package_created=False,
        limitations='Placement and lifecycle audit must pass before any update package is built.')
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('symbols','relocations')},indent=2))


if __name__=='__main__':main()
