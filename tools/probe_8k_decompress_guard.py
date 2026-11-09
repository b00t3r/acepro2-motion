"""Execute native raw-decompression size and compression-range guards only."""
import json
from unicorn.arm64_const import UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22,UC_ARM64_REG_X23,UC_ARM64_REG_X25
from livephoto_harness import Harness,ROOT


def probe(height,source_pitch,source_size,dest_pitch,dest_size,compression):
    h=Harness()
    for reg,value in ((UC_ARM64_REG_X19,source_size),(UC_ARM64_REG_X20,height),
      (UC_ARM64_REG_X21,source_pitch),(UC_ARM64_REG_X22,dest_size),
      (UC_ARM64_REG_X23,compression),(UC_ARM64_REG_X25,dest_pitch)):
        h.uc.reg_write(reg,value)
    h.stops={0x1553f70:'passed_guard',0x15540d0:'source_too_small',
             0x1554118:'destination_too_small',0x155408c:'unsupported_mode'}
    h.run(0x1553f4c)
    return dict(height=height,source_pitch=source_pitch,source_size=source_size,
       dest_pitch=dest_pitch,dest_size=dest_size,compression=compression,
       outcome=h.outcome,fragment_only=True,hardware_executed=False)


def audit():
    h,src,dst=4320,7488,15360
    return dict(cases=[probe(h,src,src*h+ds,dst,dst*h+dd,mode) for ds,dd,mode in
       ((0,0,3),(-1,0,3),(0,-1,3),(0,0,0),(0,0,9))],
       source_evidence='Camera 8K raw event: mode 3, 7680x4320, source pitch 7488.',
       limitations=['The native guard is executed with controlled buffers; no raw pixels or DSP hardware are processed.',
          'Source and destination buffer sizes are hypothetical and do not include auxiliary data or processing workspace.',
          'Passing these checks does not establish 8K still support or image quality.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/decompress-guard.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
