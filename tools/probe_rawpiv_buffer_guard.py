"""Run the native RawPiv destination-size guard with controlled sizes.

This examines one check before a decompressor call, not the full handoff.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_SP,UC_ARM64_REG_X19,UC_ARM64_REG_X21,UC_ARM64_REG_X25
from livephoto_harness import CONTEXT,Harness,ROOT


def probe(raw_pitch,raw_height,aux_pitch,aux_height,available):
    h=Harness(); sp=h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.reg_write(UC_ARM64_REG_X19,CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X21,raw_pitch)
    h.uc.reg_write(UC_ARM64_REG_X25,aux_pitch)
    h.uc.mem_write(sp+0x338,struct.pack('<I',raw_height))
    h.uc.mem_write(sp+0x358,struct.pack('<I',aux_height))
    start=0x80000000
    h.uc.mem_write(CONTEXT+0x1a90,struct.pack('<QQ',start+available,start))
    h.stops={0x76dd04:'sufficient',0x76e5a8:'insufficient'}
    h.run(0x76dce0)
    return dict(raw_pitch=raw_pitch,raw_height=raw_height,aux_pitch=aux_pitch,
      aux_height=aux_height,controlled_available=available,outcome=h.outcome,
      fragment_only=True,hardware_executed=False)


def audit():
    cases=[]
    for raw,aux,h in ((8192,2048,3072),(15360,3840,4320)):
        required=(raw+aux)*h
        cases.extend(probe(raw,h,aux,h,n) for n in (required-1,required,required+1))
    return dict(cases=cases,limitations=[
      'Only the native destination-range check ran, with controlled buffer pointers and sizes.',
      'No real 8K still event establishes the actual source dimensions, destination pitches, auxiliary layout or allocated pool.',
      'This check does not include all allocations or establish that actual compression-mode-3 decompression works.',
      'No camera or firmware changes.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/rawpiv-buffer-guard.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
