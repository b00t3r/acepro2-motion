"""Run the native calculation immediately before still-pool allocation.

The free-byte value is controlled and execution stops before allocation.
"""
import struct
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X0
from livephoto_harness import Harness


def requested_size(free_bytes):
    h = Harness()
    h.uc.mem_write(h.uc.reg_read(UC_ARM64_REG_SP) + 0x44, struct.pack('<I', free_bytes))
    h.stops = {0x280b08: 'before_allocator'}
    h.run(0x280afc)
    return h.uc.reg_read(UC_ARM64_REG_X0) & 0xffffffff
