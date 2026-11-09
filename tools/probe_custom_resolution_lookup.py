"""Try an extra Live Photo descriptor in emulator memory only.

The new descriptor deliberately resolves to today's 4:3 Live Photo resource;
it is a selection-control experiment and DOES NOT capture higher resolution.
No flashable image is produced. The test placement is not a verified code cave.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from livephoto_harness import Harness, CONTEXT, BASE, ROOT

TABLE = 0x25e4ae0
TEST_TABLE = 0x2552c40
ROW_SIZE = 28
CUSTOM_ID = 8  # An experimental backend ID; persistence and other consumers unverified.


def instruction(word):
    return struct.pack('<I', word)


def experimental_table(h):
    rows = bytes(h.uc.mem_read(TABLE, ROW_SIZE * 11))
    assert struct.unpack_from('<7I', rows, ROW_SIZE * 8) == (2, 4000, 3000, 227, 227, 7, 17)
    # Values 5120x3840 are target metadata only; native resource 227 remains
    # unchanged and still captures the current binned sensor image.
    row = struct.pack('<7I', CUSTOM_ID, 5120, 3840, 227, 227, 7, 17)
    h.uc.mem_write(TEST_TABLE, rows + row)
    page = ((TEST_TABLE & ~4095) - (0x3614cc & ~4095)) >> 12
    imm = page & 0x1fffff
    adrp_x3 = 0x90000003 | (imm & 3) << 29 | (imm >> 2) << 5
    add_x3 = 0x91000063 | (TEST_TABLE & 0xfff) << 10
    original_page = ((TABLE & ~4095) - (0x3614cc & ~4095)) >> 12
    original_imm = original_page & 0x1fffff
    expected = instruction(0x90000003 | (original_imm & 3) << 29 | (original_imm >> 2) << 5)
    if bytes(h.uc.mem_read(0x3614cc, 4)) != expected:
        raise ValueError('Unexpected native descriptor-table address')
    if bytes(h.uc.mem_read(0x3614ec, 4)) != instruction(0x71002c5f):
        raise ValueError('Unexpected native descriptor-table bound')
    h.uc.mem_write(0x3614cc, instruction(adrp_x3))
    h.uc.mem_write(0x3614d8, instruction(add_x3))
    h.uc.mem_write(0x3614ec, instruction(0x7100305f))  # cmp w2,#12


def probe(resolution, actual_mode=17, custom=False):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    if custom:
        experimental_table(h)
    h.uc.mem_write(CONTEXT, struct.pack('<I', 0xffffffff))

    def config(uc):
        key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) == (0x12, 20):
            data = struct.pack('<5I', 1, 0, 20, actual_mode, 0)
        elif (key, size) == (0x2e, 4):
            data = struct.pack('<I', resolution)
        else:
            raise ValueError('Unexpected config query %x/%d' % (key, size))
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), data)
        return 0

    h.mocks = {0x2e4380: config, 0x2639a0: lambda uc: 0,
               0x71b880: lambda uc: 0}
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.run(0x3611c0)
    return dict(resolution=resolution, actual_mode=actual_mode, experiment=custom,
                status=h.uc.reg_read(UC_ARM64_REG_X0) & 0xffffffff,
                resource_index=struct.unpack('<I', h.uc.mem_read(CONTEXT, 4))[0],
                high_resolution_capture=False)


if __name__ == '__main__':
    cases = [probe(n, custom=edit) for n in (2, 3, 6, 8) for edit in (False, True)]
    assert cases[-2]['status'] == 65535
    assert cases[-1]['status'] == 0 and cases[-1]['resource_index'] == 194
    path = ROOT / 'analysis/motion-resolution-audit/custom-lookup-probe.json'
    path.write_text(json.dumps(cases, indent=2) + '\n')
    print(json.dumps(cases, indent=2))
