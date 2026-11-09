import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_decoupling import audit


class RawFeedDecouplingTests(unittest.TestCase):
    def test_isolated_sizing_change(self):
        result = audit()
        native = result['native']
        experiment = result['experimental']
        self.assertEqual(native['controlled_flag'], 0)
        self.assertEqual(experiment['controlled_flag'], 0)
        self.assertEqual(native['raw_total_bytes'], 32 * native['raw_frame_bytes'])
        self.assertEqual(experiment['raw_total_bytes'], 5 * experiment['raw_frame_bytes'])
        self.assertEqual(result['interval_setter_for_selector_zero']['stored_interval'], 2)
        self.assertEqual(result['interval_setter_for_selector_one']['stored_interval'], 5)


if __name__ == '__main__':
    unittest.main()
