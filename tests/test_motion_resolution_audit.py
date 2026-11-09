"""Check table interpretation against independent saved hardware evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_motion_resolution import ROOT, audit, image


class MotionResolutionAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit(image())

    def test_current_live_mode_matches_hardware_log(self):
        row = self.report['sensor_modes'][36]
        self.assertEqual((row['width'], row['height'], row['hdr_type']), (4096, 3072, 2))
        log = (ROOT / 'analysis/trial-w-hardware/logs/decoded/20261029_48.log.txt').read_text()
        self.assertIn('PreMode = 36/', log)
        self.assertIn('main w 4096 h 3072', log)

    def test_full_photo_mode_matches_hardware_log(self):
        row = self.report['sensor_modes'][33]
        self.assertEqual((row['width'], row['height']), (8192, 6144))
        log = (ROOT / 'analysis/full-resolution-baseline/decoded/20261029_15.log.txt').read_text()
        self.assertIn('Config Mode: 33', log)
        self.assertIn('pitch 16384 main w 8192 h 6144', log)

    def test_intermediate_modes_are_cropped(self):
        for row in self.report['sensor_modes'][21:27]:
            self.assertEqual(row['source_rect'], [1728, 1296, 4736, 3552])
            self.assertEqual((row['width'], row['height']), (4736, 3552))

    def test_8k_mraw_labels_do_not_override_real_timing(self):
        for row in self.report['selected_formats'][-2:]:
            self.assertIn('P30', row['label'])
            self.assertTrue(row['has_memory_raw_node'])
            self.assertEqual(row['sensor_mode'], 53)
            self.assertEqual(row['configured_fps'], 5)
            self.assertEqual(self.report['sensor_modes'][53]['nominal_fps'], 5)

    def test_regular_8k_is_a_distinct_path(self):
        row = self.report['selected_formats'][0]
        self.assertEqual((row['sensor_mode'], row['configured_fps']), (20, 24))
        self.assertFalse(row['has_memory_raw_node'])
        self.assertEqual(self.report['sensor_modes'][20]['source_rect'], [0, 768, 8192, 4608])

    def test_native_live_photo_lookup_has_no_intermediate_size(self):
        live = [r for r in self.report['photo_descriptors'] if r[-1] == 17]
        self.assertEqual({r[0] for r in live}, {2, 3, 6})
        self.assertTrue(all(r[1] <= 4096 for r in live))


if __name__ == '__main__':
    unittest.main()
