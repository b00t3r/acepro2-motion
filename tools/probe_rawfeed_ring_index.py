"""Execute native raw-ring address arithmetic with controlled memory inputs."""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X19, UC_ARM64_REG_X21, UC_ARM64_REG_X22
from livephoto_harness import Harness, ROOT
from probe_rawfeed_buffer_sizing import GLOBAL


def probe(flag, counter, slot_bytes=100663296, force_five=False):
    h=Harness()
    h.uc.mem_map(0x141e9000, 0xc6000)
    h.uc.reg_write(UC_ARM64_REG_X22, GLOBAL)
    h.uc.reg_write(UC_ARM64_REG_X21, GLOBAL + 0xc3000)
    h.uc.mem_write(GLOBAL + 0xc3cb8, bytes([flag]))
    h.uc.mem_write(GLOBAL + 0x40df4, struct.pack('<I', counter))
    h.uc.mem_write(GLOBAL + 0xc202c, struct.pack('<I', slot_bytes))
    base=0x20000000
    h.uc.mem_write(GLOBAL + 0xc1ff8, struct.pack('<Q', base))
    if force_five:
        # In-memory diagnostic only: mov w28,w11 (w11 was set to five).
        original=bytes(h.uc.mem_read(0x154c69c,4))
        if original != bytes.fromhex('9c038b1a'):
            raise ValueError(f'Unexpected conditional instruction: {original.hex()}')
        h.uc.mem_write(0x154c69c,struct.pack('<I',0x2a0b03fc))
    h.uc.emu_start(0x154c678, 0x154c6c0, count=100)
    offset=h.uc.reg_read(UC_ARM64_REG_X19)-base
    return dict(controlled_flag=flag, frame_counter=counter, frame_bytes=slot_bytes, in_memory_force_five=force_five,
                selected_slot=offset//slot_bytes, offset_bytes=offset, fragment_only=True)


def audit():
    cases=[probe(flag,n) for flag in (0,1) for n in (0,4,5,31,32)]
    return dict(cases=cases, limits=['Counter, flag, addresses and frame size are controlled; no raw frames or task scheduling are executed.',
      'This identifies one ring address calculation, not every raw/CE access or ownership transition.',
      'A five-slot allocation with selector zero permits index 5 and beyond; sizing alone must not be patched.',
      'No camera execution or firmware created.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-ring-index.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
