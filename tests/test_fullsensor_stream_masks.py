import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_fullsensor_stream_masks import select, native_exact_fallback


class FullSensorStreamMaskTests(unittest.TestCase):
    def test_bitmask_selectors(self):
        self.assertEqual(select(16, 1, 0), 0x3)
        self.assertEqual(select(42, 1, 0), 0x3)
        self.assertEqual(select(16, 8, 0), 0x8)
        self.assertEqual(select(42, 8, 0), 0x2)

    def test_exact_selectors_are_not_equivalent(self):
        self.assertEqual(select(16, 8, 1), 0x8)
        self.assertEqual(select(42, 8, 1), 0)
        self.assertEqual(select(42, 9, 1), 0x2)
        self.assertEqual(select(16, 9, 1), 0)

    def test_native_fallback_handles_both_template_flag_values(self):
        ordinary = native_exact_fallback(16)
        full = native_exact_fallback(42)
        self.assertEqual((ordinary['selectors_attempted'], ordinary['one_based_selected_stream']), ([8], 4))
        self.assertEqual((full['selectors_attempted'], full['one_based_selected_stream']), ([8, 9], 2))


if __name__ == '__main__':
    unittest.main()
