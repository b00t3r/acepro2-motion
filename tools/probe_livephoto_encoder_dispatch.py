"""Correlate a saved Live Photo stream request with native dispatch branches.

The saved log proves a stream-start mask, not all downstream arguments or
encoder behavior. The isolated dispatch fragment is run with template masks.
"""
import json
import re
import struct
from unicorn.arm64_const import (UC_ARM64_REG_SP, UC_ARM64_REG_X20,
                                UC_ARM64_REG_X22, UC_ARM64_REG_X28)
from livephoto_harness import ROOT, Harness
from probe_fullsensor_stream_masks import select


def dispatch(index, requested):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    net, blue, normal = (select(index, kind, 0) for kind in (8, 0x10000000, 1))
    h.uc.reg_write(UC_ARM64_REG_X28, net)
    h.uc.reg_write(UC_ARM64_REG_X22, blue)
    h.uc.reg_write(UC_ARM64_REG_X20, requested)
    h.uc.mem_write(h.uc.reg_read(UC_ARM64_REG_SP) + 0x74, struct.pack('<I', normal))
    h.stops.update({0x27e980: 'network_or_blue_branch', 0x27ea8c: 'normal_stream_branch',
                    0x27e7dc: 'other_mask_branch'})
    h.run(0x27e7c4)
    return dict(format_index=index, requested_mask=hex(requested),
                net_mask=hex(net), blue_mask=hex(blue), normal_mask=hex(normal),
                outcome=h.outcome)


def logged_start():
    path = ROOT / 'analysis/trial-x-memory-hardware/logs/decoded/20261030_03.log.txt'
    lines = path.read_text(errors='replace').splitlines()
    for i, line in enumerate(lines):
        if 'Start pre-recording by livephoto' not in line:
            continue
        for j in range(i+1, min(i+120, len(lines))):
            match = re.search(r'<INS_STREAM> Stream Start\(mask 0x([0-9a-fA-F]+)\)', lines[j])
            if match:
                return dict(path=str(path.relative_to(ROOT)), livephoto_line=i+1,
                            stream_start_line=j+1, livephoto_text=line,
                            stream_start_text=lines[j], mask=int(match[1], 16))
    raise ValueError('No nearby Live Photo stream start in saved log')


def main():
    log = logged_start()
    report = dict(hardware_baseline=log,
        normal_request_experiment=[dispatch(i, log['mask']) for i in (16, 42)],
        individual_second_stream_experiment=[dispatch(i, 2) for i in (16, 42)],
        limitations=['The log does not prove the full-sensor camera will use the same request mask.',
                     'Branch simulation does not execute the encoder, LRV mux, ISP or full Live Photo state machine.',
                     'Photo colours, sensor timing and DSP allocations remain unvalidated.'],
        hardware_fullsensor_tested=False, firmware_changed=False)
    output = ROOT / 'analysis/motion-resolution-audit/livephoto-encoder-dispatch.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
