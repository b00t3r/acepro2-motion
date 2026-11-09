import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_selector import select


class RawFeedSelectorTests(unittest.TestCase):
    def test_profile_values_and_selector(self):
        raw_feed = select(31)
        full_sensor = select(42)
        self.assertEqual(raw_feed['view_bytes'], [0, 0, 3])
        self.assertEqual(raw_feed['selected_flag'], 0)
        self.assertEqual(full_sensor['view_bytes'], [0, 4])
        self.assertEqual(full_sensor['selected_flag'], 1)
        self.assertEqual(full_sensor['hypothetical_full_sensor_sizing']['raw_total_bytes'], 503316480)

    def test_changed_value_is_counterfactual(self):
        changed = select(31, (2, 4))
        self.assertEqual(changed['selected_flag'], 1)
        self.assertEqual(changed['hypothetical_full_sensor_sizing']['ce_total_bytes'], 125829120)
        self.assertFalse(changed['camera_executed'])


if __name__ == '__main__':
    unittest.main()
