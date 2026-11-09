"""Execute two native raw-writer address fragments with controlled data.

An in-memory selector instruction may be changed for diagnostic comparison.
No real allocation, producer, consumer, raw frame, or camera is run.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_SP
from livephoto_harness import Harness, ROOT
from probe_rawfeed_buffer_sizing import GLOBAL

SITES={
    'writer_a': (0x1548f0c,0x1548f6c,0x1548f2c),
    'writer_b': (0x154d46c,0x154d4cc,0x154d48c),
}


def probe(site, flag, counter, force_five=False):
    start,end,patch=SITES[site]
    h=Harness()
    h.uc.mem_map(0x141e9000,0xc6000)
    h.uc.reg_write(UC_ARM64_REG_X19,GLOBAL+0xc0000)
    h.uc.reg_write(UC_ARM64_REG_X20,GLOBAL+0xc3000)
    h.uc.mem_write(GLOBAL+0xc3cb8,bytes([flag]))
    h.uc.mem_write(GLOBAL+0xc1ff4,struct.pack('<I',counter))
    base=0x20000000
    h.uc.mem_write(GLOBAL+0xc1ff8,struct.pack('<Q',base))
    frame_size=100663296
    h.uc.mem_write(GLOBAL+0xc202c,struct.pack('<I',frame_size))
    if force_five:
        original=bytes(h.uc.mem_read(patch,4))
        if original != bytes.fromhex('8410821a'):
            raise ValueError(f'Unexpected select at {patch:#x}: {original.hex()}')
        h.uc.mem_write(patch,struct.pack('<I',0x2a0403e4))  # mov w4,w4
    h.uc.emu_start(start,end,count=100)
    address=h.uc.reg_read(UC_ARM64_REG_X0)
    return dict(site=site,flag=flag,counter=counter,force_five=force_five,
                selected_slot=(address-base)//frame_size, address=address,
                fragment_only=True)


def audit():
    return dict(cases=[probe(site,flag,n,force) for site in SITES
        for flag,force in ((0,False),(1,False),(0,True)) for n in (0,4,5,31,32)],
        limitations=['Inputs and flag are controlled; only writer address fragments ran.',
                     'Two further in-memory edits do not cover every raw-feed access or prove ownership is safe.',
                     'No camera, sensor, actual allocation or full task was executed.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-writer-index.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
