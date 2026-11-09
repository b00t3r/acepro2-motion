"""Run the ARM status helper with mocked conversion and FAT stat services."""
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_background_prototype import link_regions
from livephoto_harness import BASE,CONTEXT,Harness


class StatDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion';out.mkdir(parents=True,exist_ok=True)
        obj=out/'stat-detail-test.o'
        subprocess.run(['clang','-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-mgeneral-regs-only','-mno-outline-atomics','-c',str(ROOT/'tools/motion_stat_detail.c'),
            '-o',str(obj)],check=True)
        cls.entry=0x2558000
        blobs,symbols,_=link_regions([(cls.entry,cls.entry+0x1000,[obj])])
        cls.entry=symbols['motion_stat_detail'];cls.blob=blobs[0]

    def run_case(self,path_rc,stat_rc,path=True,detail=True):
        h=Harness();h.uc.mem_write(0x2558000,self.blob);calls=[]
        def convert(uc):
            calls.append('convert')
            self.assertEqual(uc.reg_read(UC_ARM64_REG_X2),1)
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X0),b'P'*24)
            return path_rc
        def stat(uc):
            calls.append('stat')
            self.assertEqual(bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X0),24)),b'P'*24)
            return stat_rc
        h.mocks={0x14e1780:convert,0x14ebd40:stat}
        h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT+0x100 if path else 0)
        h.uc.reg_write(UC_ARM64_REG_X1,CONTEXT+0x200 if detail else 0)
        h.uc.mem_write(CONTEXT+0x200,struct.pack('<I',0xaabbccdd))
        h.run(self.entry)
        return h.uc.reg_read(UC_ARM64_REG_X0)&0xffffffff,struct.unpack('<I',h.uc.mem_read(CONTEXT+0x200,4))[0],calls

    def test_present_and_distinct_controlled_errors(self):
        self.assertEqual(self.run_case(0,0),(0,0,['convert','stat']))
        self.assertEqual(self.run_case(5,2),(1,5,['convert']))
        for code in (1,2,5,49):
            self.assertEqual(self.run_case(0,code),(2,code,['convert','stat']))

    def test_invalid_arguments_cause_no_native_calls(self):
        self.assertEqual(self.run_case(0,0,path=False)[::2],(3,[]))
        self.assertEqual(self.run_case(0,0,detail=False)[::2],(3,[]))
