"""Trace the native Live Photo processing-budget assignment in isolation.

This is a controlled instruction fragment, not an end-to-end camera startup.
The budget describes DSP work area, not the separate still-image buffer pool.
"""
import json
import struct

from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_X3, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X19,
    UC_ARM64_REG_X20, UC_ARM64_REG_X25, UC_ARM64_REG_X26)
from livephoto_harness import CONTEXT, Harness, ROOT
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE


def probe(resource, capture_id):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    cfg = CONTEXT + 0x18cfc
    h.uc.mem_write(cfg + 6, struct.pack('<H', resource))
    h.uc.mem_write(cfg + 8, struct.pack('<H', capture_id))
    h.uc.mem_write(CONTEXT + 0x18ce0, bytes(8))
    h.uc.reg_write(UC_ARM64_REG_X20, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X26, cfg)
    h.stops[0x28cb24] = 'live_budget_assigned'
    h.stops[0x28cdcc] = 'other_resource_path'
    h.run(0x28caf0)
    budget = struct.unpack('<Q', h.uc.mem_read(CONTEXT + 0x18ce0, 8))[0]
    return dict(resource=resource, capture_id=capture_id, outcome=h.outcome,
                budget_bytes=budget, budget_hex=hex(budget))


def setter_arguments(capture_id, budget=0x74000000):
    """Execute native format-ID search up to the setter call boundary."""
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    h.uc.mem_map(0x12100000, 0x1000)
    h.uc.mem_write(CONTEXT + 0x18ce0, struct.pack('<Q', budget))
    for reg, value in ((UC_ARM64_REG_X0, capture_id), (UC_ARM64_REG_X1, 0),
                       (UC_ARM64_REG_X2, FORMAT_BASE - 0x20 + 0x18cfa),
                       (UC_ARM64_REG_X3, 0xffff), (UC_ARM64_REG_X5, 62),
                       (UC_ARM64_REG_X6, FORMAT_STRIDE), (UC_ARM64_REG_X19, 0),
                       (UC_ARM64_REG_X25, CONTEXT + 0x18000)):
        h.uc.reg_write(reg, value)
    h.stops[0x15db4a0] = 'setter_entry'
    h.stops[0x28d310] = 'format_not_found'
    h.stops[0x28d31c] = 'invalid_selection'
    h.run(0x28cc00)
    return dict(capture_id=capture_id, outcome=h.outcome,
                format_index=h.uc.reg_read(UC_ARM64_REG_X0),
                assigned_budget=h.uc.reg_read(UC_ARM64_REG_X1))


def main():
    cases = [probe(227, 30), probe(227, 49), probe(226, 31), probe(21, 18)]
    result = dict(cases=cases, setter_argument_experiment=[setter_arguments(i) for i in (30, 49)],
        interpretation='In isolated native fragments the Live resource, not capture ID, selects a 0x74000000-byte DSP budget; the format search passes that budget and the matching format index to the native setter. Full end-to-end execution has not been established.',
        comparison='A saved ordinary full-resolution photo log reports 0x80000000 bytes for format 12. This comparison does not establish the minimum or required budget for format 42.',
        hardware_tested=False, firmware_changed=False)
    out = ROOT / 'analysis/motion-resolution-audit/livephoto-dsp-budget.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
