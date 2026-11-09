import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_still_raw_pitch import probe


class StillRawPitchTests(unittest.TestCase):
    def test_matches_recorded_4k_and_8k_pitch(self):
        self.assertEqual(probe(4096,0)['pitch_bytes'],8192)
        self.assertEqual(probe(7680,3)['pitch_bytes'],7488)
        self.assertEqual(probe(8192,0)['pitch_bytes'],16384)


if __name__=='__main__':
    unittest.main()
