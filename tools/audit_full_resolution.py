"""Execute native resource selection; no firmware modifications or camera writes."""
import json
import struct
from pathlib import Path

from livephoto_harness import Harness, CONTEXT
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2


def select_photo_resource(resolution, actual_mode):
    if actual_mode not in (12, 17):
        raise ValueError('Audit supports normal and Live Photo modes only')
    h = Harness()
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.mem_write(CONTEXT, struct.pack('<I', 0xffffffff))

    def config(uc):
        key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) == (0x12, 20):
            data = struct.pack('<5I', 1, 0, 20, actual_mode, 0)
        elif (key, size) == (0x2e, 4):
            data = struct.pack('<I', resolution)
        else:
            raise ValueError('Unexpected native config query: %x/%d' % (key, size))
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), data)
        return 0

    h.mocks = {0x2e4380: config, 0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.run(0x3611c0)
    index = struct.unpack('<I', h.uc.mem_read(CONTEXT, 4))[0]
    result = {'photo_resolution_id': resolution, 'actual_mode': actual_mode,
              'status': h.uc.reg_read(UC_ARM64_REG_X0) & 0xffffffff,
              'resource_index': index, 'hardware_executed': False}
    if result['status'] == 0:
        address = (0x25e4ae0 + 28*index if actual_mode == 12
                   else 0x194ffd8 + 124*index)
        count = 7 if actual_mode == 12 else 31
        result['descriptor'] = list(struct.unpack('<%dI' % count, h.uc.mem_read(address, count*4)))
    return result


if __name__ == '__main__':
    results = [select_photo_resource(res, mode) for mode in (12, 17) for res in (3, 5)]
    output = Path(__file__).resolve().parents[1] / 'analysis/full-resolution-baseline/resource-selection.json'
    output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
