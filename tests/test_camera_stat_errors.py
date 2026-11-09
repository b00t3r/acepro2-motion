"""Execute the camera's native stat wrapper with mocked lower-level results."""
import sys
import unittest
from pathlib import Path
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from livephoto_harness import Harness,CONTEXT


class StatErrorsTests(unittest.TestCase):
    def stat_result(self,underlying):
        h=Harness()
        h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT+0x100)
        h.uc.reg_write(UC_ARM64_REG_X1,CONTEXT+0x200)
        h.mocks={0x14df8a0:lambda uc:underlying}
        h.run(0x26aac0)
        return h.uc.reg_read(UC_ARM64_REG_X0)&0xffffffff

    def test_wrapper_collapses_distinct_errors(self):
        self.assertEqual(self.stat_result(0),0)
        self.assertEqual(self.stat_result(1),0x110004)
        self.assertEqual(self.stat_result(5),0x110004)
        self.assertEqual(self.stat_result(0xffffffff),0x110004)
