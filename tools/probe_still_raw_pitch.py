"""Run firmware pitch query with native arithmetic and mocked system services.

Compression inputs are controlled. This does not validate actual DSP formats,
hardware buffer availability, or any image capture.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3
from livephoto_harness import CONTEXT, Harness, ROOT


def probe(width, compression):
    h=Harness()
    h.mocks={0xfdc3e0:lambda uc:0,0xfe3b20:lambda uc:0,0x104b1c0:lambda uc:0}
    for reg,value in ((UC_ARM64_REG_X0,width),(UC_ARM64_REG_X1,compression),
                      (UC_ARM64_REG_X2,CONTEXT),(UC_ARM64_REG_X3,CONTEXT+2)):
        h.uc.reg_write(reg,value)
    h.run(0x103f820)
    height_or_width,pitch=struct.unpack('<HH',h.uc.mem_read(CONTEXT,4))
    return dict(width=width,controlled_compression=compression,
                output_first=height_or_width,pitch_bytes=pitch,
                status=h.uc.reg_read(UC_ARM64_REG_X0),
                mocks=[hex(x) for x in sorted(h.mocks)],hardware_executed=False)


def audit():
    return dict(cases=[probe(w,c) for w in (4096,7680,8192) for c in (0,3)],
        limitations=['Native fallback arithmetic ran with DSP hooks and status service mocked.',
          'Compression input 3 is suggested by a stream log; its equivalence to still raw format has not been verified.',
          'Pitch alone is not an allocation size and does not establish raw/CE planes, alignment or available memory.',
          'No sensor, DSP capture, allocator, encoder or camera ran.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/still-raw-pitch.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
