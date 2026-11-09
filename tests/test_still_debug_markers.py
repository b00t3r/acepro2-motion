"""Execute native SD-marker parsing and intermediate-image dump dispatch."""
import sys
import struct
import unittest
from pathlib import Path
from unicorn.arm64_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from livephoto_harness import Harness,CONTEXT

MARKERS=('INS_STILL_CAP_DEBUG_ITUNER','INS_STILL_CAP_DEBUG_R2Y','INS_STILL_CAP_DEBUG_YUV')
CONTROL=0x1281fc70


def setup(markers):
    h=Harness()
    h.uc.mem_map(0x1281f000,0x1000)
    queried=[]
    def stat(uc):
        ptr=uc.reg_read(UC_ARM64_REG_X0)
        path=bytes(uc.mem_read(ptr,100)).split(b'\0')[0].decode()
        queried.append(path)
        return 0 if path in {'C:\\'+m for m in markers} else 1
    def zero(uc):
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X0),bytes(uc.reg_read(UC_ARM64_REG_X2)))
        return 0
    h.mocks={0x17c0440:zero,0x26aac0:stat,0x2639a0:lambda uc:0,0x71b880:lambda uc:0}
    h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT)
    h.run(0x75bae0)
    return h,queried


class StillDebugMarkersTests(unittest.TestCase):
    def test_no_markers_leaves_debug_disabled(self):
        h,_=setup(())
        # Byte zero means initialized; byte one gates active dump behaviour.
        self.assertEqual(bytes(h.uc.mem_read(CONTROL,8)),bytes([1,0,0,0,0,0,0,0]))
        self.assertEqual(struct.unpack('<Q',h.uc.mem_read(CONTROL+8,8))[0],CONTEXT)

    def test_selected_markers_enable_only_ituner_r2y_and_final_yuv(self):
        h,queried=setup(MARKERS)
        self.assertEqual(bytes(h.uc.mem_read(CONTROL,8)),bytes([1,1,1,0,0,1,1,0]))
        for m in MARKERS:
            self.assertIn('C:\\'+m,queried)

    def test_native_r2y_and_final_dump_use_yuv420_sizes_and_native_mux(self):
        for kind,width,height in ((4,4096,3072),(8,4096,2304)):
            h,_=setup(MARKERS)
            desc=CONTEXT+0x100
            buf=CONTEXT+0x200
            h.uc.mem_write(desc,struct.pack('<I4xQ',kind,buf))
            h.uc.mem_write(buf+8,struct.pack('<QQ',0xf5616e00,0xf6216e00))
            h.uc.mem_write(buf+0x18,struct.pack('<H',width))
            h.uc.mem_write(buf+0x1e,struct.pack('<HH',width,height))
            calls=[]
            def dump(uc):
                calls.append(tuple(uc.reg_read(r) for r in (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2)))
                return 0
            h.mocks[0x756960]=dump
            h.uc.reg_write(UC_ARM64_REG_X0,desc)
            h.run(0x75aea0)
            self.assertEqual(calls,[(0xf2,0xf5616e00,width*height*3//2)])
