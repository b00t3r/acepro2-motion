import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_fullsensor_stream_layout import inspect


class FullSensorStreamLayoutTests(unittest.TestCase):
    def test_template_switch_changes_stream_topology(self):
        live, full = inspect(16), inspect(42)
        self.assertEqual((live['stream_count'], live['stream_mask']), (4, '0xf'))
        self.assertEqual((full['stream_count'], full['stream_mask']), (2, '0x3'))
        self.assertEqual(live['streams'][1]['canvas'], [1280, 960])
        self.assertEqual(full['streams'][1]['canvas'], [1280, 960])
        self.assertEqual(full['streams'][0]['canvas'], [8160, 6144])

    def test_full_sensor_template_has_distinct_input_and_recording_rates(self):
        full = inspect(42)
        self.assertEqual(full['sensor_rate_words'], [5000, 1000])
        self.assertEqual(full['streams'][0]['frame_rate_words'], [30000, 1001])
        self.assertEqual(full['streams'][1]['frame_rate_words'], [30000, 1001])


if __name__ == '__main__':
    unittest.main()
