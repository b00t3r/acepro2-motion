"""Offline probe of native stat's per-task error slot with controlled services.

The real FAT lookup is mocked; numeric codes are examples, not mappings.
"""
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1
from livephoto_harness import CONTEXT,Harness


def probe(error,through_wrapper=False):
    h=Harness();task=CONTEXT+0x1000;drive=CONTEXT+0x8000
    h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT+0x100)
    h.uc.reg_write(UC_ARM64_REG_X1,CONTEXT+0x200)
    h.mocks={0x1501a80:lambda uc:task,0x14fd7a0:lambda uc:drive,
        0x1079f20:lambda uc:0,0x1079fa0:lambda uc:0,
        0x15012e0:lambda uc:0,0x1501cc0:lambda uc:0,
        0x14ebc60:lambda uc:error,0x14e1780:lambda uc:0}
    h.run(0x26aac0 if through_wrapper else 0x14ebd40)
    return {'controlled_lookup_result':error,
            'native_return':h.uc.reg_read(UC_ARM64_REG_X0)&0xffffffff,
            'task_error':struct.unpack('<I',h.uc.mem_read(task+0x4ea8,4))[0],
            'through_wrapper':through_wrapper,'hardware_executed':False}


def probe_path_conversion_failure(error=5):
    h=Harness();task=CONTEXT+0x1000
    h.uc.mem_map(0xf03a000,0x1000)
    h.uc.mem_write(task+0x4ea8,struct.pack('<I',0x12345678))
    h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT+0x100)
    h.uc.reg_write(UC_ARM64_REG_X1,CONTEXT+0x200)
    h.mocks={0x14e1780:lambda uc:error}
    h.run(0x26aac0)
    return {'wrapper_return':h.uc.reg_read(UC_ARM64_REG_X0)&0xffffffff,
            'task_error':struct.unpack('<I',h.uc.mem_read(task+0x4ea8,4))[0],
            'global_conversion_error':struct.unpack('<I',h.uc.mem_read(0xf03a008,4))[0]}
