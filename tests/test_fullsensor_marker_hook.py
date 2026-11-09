import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_fullsensor_marker_hook import run
from probe_fullsensor_marker_hook import image_and_symbols
from livephoto_harness import run_livephoto_config, CONTEXT, ROOT
from unicorn.arm64_const import UC_ARM64_REG_X2
import struct


class FullSensorMarkerHookTests(unittest.TestCase):
    def test_guard_and_machine_state(self):
        cases = ((227, 1, True, True, [49, 49], ['open', 'close']),
                 (227, 1, False, True, [30, 30], ['open']),
                 (227, 1, True, False, [30, 30], ['open', 'close']),
                 (227, 0, True, True, [30, 30], []),
                 (226, 1, True, True, [30, 30], []))
        for resource, narrow, present, close_ok, ids, calls in cases:
            result = run(resource, narrow, present, close_ok)
            self.assertEqual(result['ids'], ids)
            self.assertEqual(result['calls'], calls)
            self.assertEqual(result['outcome'], 'native_continuation')
            for key in ('registers_preserved', 'vectors_preserved', 'flags_preserved', 'stack_preserved'):
                self.assertTrue(result[key], key)

    def test_complete_config_routine_with_marker_present_or_absent(self):
        candidate, _, _ = image_and_symbols()
        original = (ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes()
        for present in (False, True):
            def open_mock(uc):
                if present:
                    uc.mem_write(uc.reg_read(UC_ARM64_REG_X2), struct.pack('<Q', CONTEXT+0x500))
                return 0 if present else 1
            mocks = {0x26a860: open_mock, 0x26a8a0: lambda uc: 0}
            before = run_livephoto_config(227, 1, image_data=original, include_encoding=True)
            after = run_livephoto_config(227, 1, image_data=candidate, include_encoding=True, extra_mocks=mocks)
            expected = bytearray.fromhex(before['packed_config_hex'])
            if present: struct.pack_into('<HH', expected, 8, 49, 49)
            self.assertEqual(after['packed_config_hex'], expected.hex())


if __name__ == '__main__':
    unittest.main()
