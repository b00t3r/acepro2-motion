"""Check the offline diagnostic guard and its ARM64 register contract."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from unicorn.arm64_const import *
from livephoto_harness import Harness, ROOT, CONTEXT
from probe_guarded_fullsensor import HOOK, experimental_image, probe


class GuardedFullSensorProbeTests(unittest.TestCase):
    def test_native_configuration_matrix(self):
        result = probe()
        self.assertFalse(result['firmware_package_created'])
        self.assertEqual(sum(c['original_ids'] != c['experimental_ids'] for c in result['cases']), 1)

    def test_guard_preserves_registers_flags_and_stack(self):
        original = (ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes()
        modified = experimental_image(original)
        for resource, narrow in ((227, 1), (227, 0), (226, 1), (227, 2)):
            h = Harness(modified)
            cfg = CONTEXT + 0x1000
            h.uc.mem_write(cfg, bytes(0x70))
            h.uc.mem_write(cfg + 6, struct.pack('<H', resource))
            h.uc.mem_write(cfg + 0x34, struct.pack('<H', narrow))
            regs = [globals()['UC_ARM64_REG_X%d' % i] for i in range(31)]
            for i, reg in enumerate(regs):
                h.uc.reg_write(reg, 0x1234000000000000 + i)
            h.uc.reg_write(UC_ARM64_REG_X0, 30)
            h.uc.reg_write(UC_ARM64_REG_X19, cfg)
            h.uc.reg_write(UC_ARM64_REG_NZCV, 0xa0000000)
            before = [h.uc.reg_read(r) for r in regs]
            sp = h.uc.reg_read(UC_ARM64_REG_SP)
            h.stops[HOOK+4] = 'done'
            h.run(HOOK)
            self.assertEqual([h.uc.reg_read(r) for r in regs], before)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP), sp)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_NZCV), 0xa0000000)
            expected = (49, 49) if (resource, narrow) == (227, 1) else (0, 30)
            self.assertEqual(struct.unpack('<HH', h.uc.mem_read(cfg+8, 4)), expected)


if __name__ == '__main__':
    unittest.main()
