import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_8k_still_setup import probe


class StillSetupTests(unittest.TestCase):
    def test_pitch_arguments_and_alternate_branch(self):
        for width, compression in ((4096, 0), (7680, 3), (7680, 0)):
            result = probe(width, compression)
            self.assertEqual((result['outcome'], result['pitch_width'], result['pitch_compression']),
                             ('before_pitch_call', width, compression))
        self.assertEqual(probe(7680, 3, 1)['outcome'], 'alternate_path')
