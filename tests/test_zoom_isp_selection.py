"""Regression evidence for the green-shot investigation, using stock ARM64."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_zoom_isp_selection import replay, filter_headers


class ZoomIspSelectionTests(unittest.TestCase):
    def test_stock_selector_reproduces_both_logged_rows(self):
        before, after = replay(1), replay(0)
        self.assertEqual(before['row'], 465)
        self.assertEqual(before['table'], 'g_isp_ik_table_normalshot_livephoto')
        self.assertEqual(after['row'], 420)
        self.assertEqual(after['table'], 'g_isp_ik_table_normalshot_zoom')
        self.assertEqual({k for k in before['inputs'] if before['inputs'][k] != after['inputs'][k]}, {'recording'})

    def test_table_filter_values_match_the_observed_change(self):
        values = filter_headers()
        for key in ('live_default', 'live_face'):
            self.assertEqual(values[key]['parameter_id'], 24)
            self.assertEqual(values[key]['first_40_values'], [-64])
        for key in ('zoom_default', 'zoom_face'):
            self.assertEqual(values[key]['parameter_id'], 24)
            self.assertEqual(values[key]['first_40_values'], [-1024])


if __name__ == '__main__':
    unittest.main()
