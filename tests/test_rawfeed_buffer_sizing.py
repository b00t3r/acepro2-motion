import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_buffer_sizing import probe


class RawFeedBufferSizingTests(unittest.TestCase):
    def test_native_fragment_matches_trial_h_log(self):
        case = probe(8192, 6144, 1)
        self.assertEqual(case['raw_total_bytes'], 503316480)
        self.assertEqual(case['ce_total_bytes'], 125829120)

    def test_flag_changes_frame_count(self):
        for width, height in ((4096, 3072), (8192, 6144)):
            for flag, count in ((0, 32), (1, 5)):
                case = probe(width, height, flag)
                self.assertEqual(case['raw_total_bytes'], count * case['raw_frame_bytes'])
                self.assertEqual(case['ce_total_bytes'], count * case['ce_frame_bytes'])


if __name__ == '__main__':
    unittest.main()
