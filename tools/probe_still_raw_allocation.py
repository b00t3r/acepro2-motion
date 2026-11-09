"""Run the native still raw-plus-CE sizing fragment with controlled inputs.

Actual pool allocation, ownership, raw delivery, and image processing are not
executed. DSP pitch hooks and their status reporting are mocked.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_SP,UC_ARM64_REG_X26,UC_ARM64_REG_X28
from livephoto_harness import CONTEXT,Harness,ROOT
from probe_still_raw_pitch import probe as pitch


def probe(width,height,compression):
    h=Harness(); cfg=CONTEXT+0x18000
    h.uc.mem_write(cfg+0x7f4,bytes([compression]))
    h.uc.reg_write(UC_ARM64_REG_X26,cfg)
    h.uc.reg_write(UC_ARM64_REG_X28,width)
    sp=h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp+0x60,struct.pack('<I',height))
    h.mocks={0xfdc3e0:lambda uc:0,0xfe3b20:lambda uc:0,0x104b1c0:lambda uc:0}
    h.stops={0x281480:'before_logging'}
    h.run(0x2813e8)
    return dict(width=width,height=height,controlled_compression=compression,
      raw_plus_aux_bytes=h.uc.reg_read(UC_ARM64_REG_X26)&0xffffffff,
      raw_pitch=pitch((width+63)&~63,compression)['pitch_bytes'],
      quarter_width_aux_pitch=pitch(((width//4)+63)&~63,compression)['pitch_bytes'],
      status=h.outcome,hardware_executed=False)


def audit():
    return dict(cases=[probe(w,h,c) for w,h in ((4096,3072),(7680,4320),(8192,4608)) for c in (0,3)],
       limitations=['The native sizing fragment runs with controlled dimensions and compression; DSP hooks and status service are mocked.',
        'A hypothetical 8K still is not known to use these settings or auxiliary data format.',
        'This number covers one calculated raw-plus-aux buffer only; it excludes video, decompression workspace, YUV, JPEG, PureShot and allocator overhead.',
        'No physical memory reservation, raw handoff, hardware, or complete camera pipeline was executed.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/still-raw-allocation.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
