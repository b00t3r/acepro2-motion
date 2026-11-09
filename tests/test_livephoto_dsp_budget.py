import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_livephoto_dsp_budget import probe, setter_arguments


class LivePhotoDspBudgetTests(unittest.TestCase):
    def test_live_resource_budget_is_independent_of_capture_id(self):
        for capture_id in (30, 49):
            result = probe(227, capture_id)
            self.assertEqual(result['outcome'], 'live_budget_assigned')
            self.assertEqual(result['budget_bytes'], 0x74000000)
        self.assertEqual(probe(21, 18)['outcome'], 'other_resource_path')

    def test_format_search_passes_same_budget_to_selected_format(self):
        for capture_id, index in ((30, 16), (49, 42)):
            result = setter_arguments(capture_id)
            self.assertEqual(result['outcome'], 'setter_entry')
            self.assertEqual(result['format_index'], index)
            self.assertEqual(result['assigned_budget'], 0x74000000)


if __name__ == '__main__':
    unittest.main()
