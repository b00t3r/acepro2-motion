import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_still_raw_allocation import probe


class StillRawAllocationTests(unittest.TestCase):
    def test_matches_camera_logged_sizes(self):
        self.assertEqual(probe(4096,3072,0)['raw_plus_aux_bytes'],31457280)
        self.assertEqual(probe(7680,4320,3)['raw_plus_aux_bytes'],40642560)

    def test_uncompressed_8k_calculation(self):
        case=probe(7680,4320,0)
        self.assertEqual(case['raw_plus_aux_bytes'],82944000)
        self.assertFalse(case['hardware_executed'])


if __name__=='__main__':
    unittest.main()
