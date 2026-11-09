"""Execute native recording and pre-recording selection with explicit config mocks.

This does not emulate asynchronous encoder, file-writer, or album tasks.
"""
import json
import struct
from livephoto_harness import Harness, CONTEXT
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3


def context(h, count):
    h.uc.mem_write(CONTEXT+0xd5c8, struct.pack('<I', count))
    for i in range(count):
        h.uc.mem_write(CONTEXT+0xd5d4+0x500*i, struct.pack('<I', 1))


def record_mask(configured_mask, count=2):
    h = Harness()
    context(h, count)
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT+0x100)
    def config(uc):
        if (uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)) != (0x17, 4):
            raise ValueError('Unexpected native config read')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), struct.pack('<I', configured_mask))
        return 0
    h.mocks = {0x2e4380: config, 0x15c3420: lambda uc: CONTEXT,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.run(0x3005c0)
    return struct.unpack('<I', h.uc.mem_read(CONTEXT+0x100, 4))[0]


def prerecord_stream_ids(count=2):
    h = Harness()
    context(h, count)
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1, 1)
    h.uc.reg_write(UC_ARM64_REG_X2, 0)
    h.run(0x28e160)
    mask = h.uc.reg_read(UC_ARM64_REG_X0)
    h.uc.reg_write(UC_ARM64_REG_X0, 4)
    h.uc.reg_write(UC_ARM64_REG_X1, mask)
    h.uc.reg_write(UC_ARM64_REG_X2, CONTEXT+0x100)
    h.uc.reg_write(UC_ARM64_REG_X3, CONTEXT+0x110)
    h.outcome = None
    h.run(0x728020)
    total = struct.unpack('<I', h.uc.mem_read(CONTEXT+0x100, 4))[0]
    return list(struct.unpack('<%dH' % total, h.uc.mem_read(CONTEXT+0x110, total*2)))


if __name__ == '__main__':
    print(json.dumps({'recording_mask_requested_lrv_only': record_mask(2),
                      'prerecord_streams_still_selected': prerecord_stream_ids(),
                      'hardware_executed': False}, indent=2))
