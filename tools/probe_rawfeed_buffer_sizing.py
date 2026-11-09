"""Run the native raw-feed sizing fragment, with controlled memory inputs.

No camera services, allocation, sensor, encoder, or complete task are run.
The branch-controlling byte is supplied by the test; its origin is not proven.
"""
import json
import struct
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X19, UC_ARM64_REG_X22
from livephoto_harness import CONTEXT, ROOT, Harness

START = 0x15469b8
END = 0x1546a70
GLOBAL = 0x141e96f0


def probe(width, height, flag, force_five=False):
    h = Harness()
    h.uc.mem_map(0x141e9000, 0xc6000)
    h.uc.mem_write(CONTEXT, struct.pack('<HH', width, height))
    h.uc.reg_write(UC_ARM64_REG_X19, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X22, GLOBAL)
    h.uc.mem_write(GLOBAL + 0xc3cb8, bytes([flag]))
    if force_five:
        # In-memory diagnostic only: replace conditional choice with mov w6,w28.
        # w28 is set to 5 by this same native fragment.
        original = bytes(h.uc.mem_read(0x1546a08, 4))
        if original != bytes.fromhex('8613861a'):
            raise ValueError(f'Unexpected conditional instruction: {original.hex()}')
        h.uc.mem_write(0x1546a08, struct.pack('<I', 0x2a1c03e6))
    h.stops = {END: 'fragment_complete'}
    h.uc.emu_start(START, END, count=100)
    fields = struct.unpack('<15I', bytes(h.uc.mem_read(GLOBAL + 0xc2020, 60)))
    return dict(width=width, height=height, controlled_flag=flag, in_memory_force_five=force_five,
                raw_pitch=fields[0], raw_frame_bytes=fields[3],
                raw_total_bytes=fields[5], ce_frame_bytes=fields[12],
                ce_total_bytes=fields[14], fragment_only=True)


def audit():
    cases = [probe(w, h, flag) for w, h in [(4096,3072),(8192,6144)] for flag in (0,1)]
    return dict(cases=cases,
        evidence='Trial H log reports 503316480 raw and 125829120 CE bytes for 8192x6144.',
        limitations=['Only native sizing instructions are executed; input dimensions and flag are controlled.',
                     'The flag source and its value for a proposed 30 fps configuration are not established.',
                     'Memory allocation, frame ownership, encoder, ISP and camera execution are not tested.',
                     'Matching the logged byte count does not establish why the camera restarted.'])


if __name__ == '__main__':
    result = audit()
    out = ROOT / 'analysis/motion-resolution-audit/rawfeed-sizing.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
