import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawpiv_resolution import probe, ROOT, BASE, image


class RawPivResolutionProbe(unittest.TestCase):
    def test_selector_is_unchanged_in_hardware_tested_trial_w(self):
        working = (ROOT / 'builds/offline-background-save/main_threadx.bin').read_bytes()
        start, end = 0x287a80 - BASE, 0x287e5c - BASE
        self.assertEqual(working[start:end], image()[start:end])

    def test_8k_video_is_overridden_to_live_binned_mode(self):
        result = probe(7)
        self.assertEqual(result['status'], 0)
        self.assertEqual(result['before']['sensor_mode'], 20)
        self.assertEqual(result['after']['sensor_mode'], 36)
        self.assertEqual(result['after']['capture_sensor_mode'], 36)
        self.assertEqual(result['after']['raw_size'], [0, 0])

    def test_full_resolution_mraw_size_survives_with_incompatible_mode(self):
        result = probe(42)
        self.assertEqual(result['before']['sensor_mode'], 53)
        self.assertEqual(result['after']['sensor_mode'], 36)
        self.assertEqual(result['after']['raw_size'], [8192, 6144])

    def test_narrow_also_overrides_high_resolution_mode(self):
        for index in (7, 15, 42):
            with self.subTest(format_index=index):
                result = probe(index, narrow=1)
                self.assertEqual(result['after']['sensor_mode'], 27)
                self.assertEqual(result['after']['capture_sensor_mode'], 27)

    def test_current_wide_live_dimensions_match_hardware(self):
        result = probe(15)
        self.assertEqual(result['after']['sensor_mode'], 36)
        self.assertEqual(result['after']['raw_size'], [4096, 3072])

    def test_full_sensor_template_can_remain_consistent_in_memory_only(self):
        for narrow in (0, 1):
            with self.subTest(narrow=narrow):
                result = probe(42, narrow=narrow, experimental_full_mode=53)
                self.assertEqual(result['status'], 0)
                self.assertEqual(result['after']['sensor_mode'], 53)
                self.assertEqual(result['after']['capture_sensor_mode'], 53)
                self.assertEqual(result['after']['iq_mode'], 95)
                self.assertEqual(result['after']['raw_size'], [8192, 6144])
                self.assertFalse(result['hardware_executed'])

    def test_unscoped_experiment_rejects_other_templates(self):
        with self.assertRaises(ValueError):
            probe(16, experimental_full_mode=53)

    def test_special_mode_flag_still_overrides_experimental_full_sensor(self):
        result = probe(42, experimental_full_mode=53, special_mode_flag=1)
        self.assertEqual(result['after']['sensor_mode'], 36)
        self.assertEqual(result['after']['capture_sensor_mode'], 36)
        self.assertEqual(result['after']['raw_size'], [8192, 6144])
        self.assertFalse(result['hardware_executed'])


if __name__ == '__main__':
    unittest.main()
