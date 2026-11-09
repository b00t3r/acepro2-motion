"""Execute the native raw-decompression config routine with simulated logging.

This only validates software configuration. No decompression hardware runs.
"""
import json
import struct
from unicorn.arm64_const import (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5)
from livephoto_harness import Harness, ROOT
from probe_still_raw_pitch import probe as pitch


def probe(width,height,source_mode,dest_mode,src_pitch,dst_pitch):
    h=Harness();h.uc.mem_map(0x142ad000,0x1000)
    h.mocks={0xdcc460:lambda uc:0}
    for reg,val in zip((UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,
                        UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5),
                       (width,height,source_mode,dest_mode,src_pitch,dst_pitch)):
        h.uc.reg_write(reg,val)
    h.run(0x1553bc0)
    state=bytes(h.uc.mem_read(0x142ad6a8,0x28))
    return dict(width=width,height=height,source_mode=source_mode,dest_mode=dest_mode,
      src_pitch=src_pitch,dst_pitch=dst_pitch,status=h.uc.reg_read(UC_ARM64_REG_X0),
      stored_modes=list(state[0x20:0x22]), work_mode=struct.unpack_from('<I',state,0x24)[0],
      mocked_services=['logging'],hardware_executed=False)


def audit():
    compressed=pitch(7680,3)['pitch_bytes']; plain=pitch(7680,0)['pitch_bytes']
    return dict(cases=[probe(7680,4320,mode,0,compressed,plain) for mode in (0,3,7)],
      limitations=['Native config helper and pitch arithmetic executed with logging and DSP hooks mocked; no actual decompression was performed.',
        'Accepting a parameter is not proof that the DSP accepts mode 3, or that its pixels, Bayer format and pitch match the real 8K stream.',
        '8K stream RawComp 3 may not be identical to the source mode of a future still snapshot.',
        'No allocator, sensor, full still pipeline or camera was exercised.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/raw-decompress-config.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
