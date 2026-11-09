import sys
import unittest
import lz4.frame
from pathlib import Path
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X2, UC_ARM64_REG_X19, UC_ARM64_REG_X30

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_record_pool_diagnostic_offline import build, HOOK, OUT, STATE
from build_record_pool_diagnostic_candidate import package, DEST
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_harness import Harness


class RecordPoolDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()
        cls.data = (OUT / 'main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def test_gate_and_register_restoration(self):
        for enabled in (0, 1):
            h = Harness(self.data)
            h.uc.mem_write(STATE, bytes([enabled]))
            h.uc.reg_write(UC_ARM64_REG_X19, 37)
            old_sp, old_lr = h.uc.reg_read(UC_ARM64_REG_SP), h.uc.reg_read(UC_ARM64_REG_X30)
            h.mocks = {0xdca900: lambda uc: 0}
            h.stops = {HOOK + 4: 'continue'}
            h.run(HOOK)
            self.assertEqual(h.outcome, 'continue')
            self.assertEqual(h.calls, [0xdca900] if enabled else [])
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X2), 3000)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP), old_sp)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X30), old_lr)

    def test_packaged_image_is_tested_image_with_usb_marker(self):
        package()
        packed = unpack_package(DEST.read_bytes())
        actual = bytearray(lz4.frame.decompress(packed['parts'][0]['payload']))
        expected = bytearray(self.data)
        for offset in USB_OFFSETS:
            self.assertEqual(actual[offset:offset+18], b'Insta360 Ace Pro s')
            expected[offset:offset+18] = b'Insta360 Ace Pro s'
        self.assertEqual(actual, expected)
