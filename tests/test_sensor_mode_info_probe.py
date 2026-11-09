import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_sensor_mode_info import probe


class SensorModeInfoProbeTests(unittest.TestCase):
    def test_full_sensor_30fps_descriptor_has_a_different_bayer_code(self):
        fast, observed_photo = probe(16), probe(33)
        self.assertEqual((fast['native_output_width'], fast['native_output_height']), (8192, 6144))
        self.assertEqual(fast['native_frame_rate_words'], [0, 30000, 1001])
        self.assertEqual((fast['native_bayer_code'], observed_photo['native_bayer_code']), (0, 2))
        self.assertFalse(fast['sensor_or_dsp_executed'])

    def test_verified_full_sensor_template_is_five_fps(self):
        self.assertEqual(probe(53)['native_frame_rate_words'], [0, 5000, 1000])


if __name__ == '__main__':
    unittest.main()
