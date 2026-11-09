"""Run the native still-processing width-to-tile decision offline.

DSP initialization is mocked at its call boundary. This probe does not
validate actual hardware limits, allocations, resizing or pixel processing.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from livephoto_harness import Harness, CONTEXT, ROOT


def probe(width):
    if not 0 < width <= 8192:
        raise ValueError('Width outside audited sensor range')
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    call = {}

    def memset(uc):
        dest = uc.reg_read(UC_ARM64_REG_X0)
        value = uc.reg_read(UC_ARM64_REG_X1) & 255
        size = uc.reg_read(UC_ARM64_REG_X2)
        uc.mem_write(dest, bytes([value]) * size)
        return dest

    def configure(uc):
        pointer = uc.reg_read(UC_ARM64_REG_X1)
        call['native_words'] = list(struct.unpack('<III', uc.mem_read(pointer, 12)))
        return 0

    h.mocks = {0x17c0440: memset, 0x2639a0: lambda uc: 0,
               0x71b880: lambda uc: 0, 0xf142e0: configure}
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, width)
    h.run(0x7575e0)
    if 'native_words' not in call:
        raise ValueError('Native DSP configuration boundary was not reached')
    return dict(width=width, configuration_words=call['native_words'],
                hardware_executed=False, dsp_call_mocked=True)


if __name__ == '__main__':
    cases = [probe(w) for w in (2048, 4096, 5120, 8192)]
    output = ROOT / 'analysis/motion-resolution-audit/still-processing-tiles.json'
    output.write_text(json.dumps(cases, indent=2) + '\n')
    print(json.dumps(cases, indent=2))
