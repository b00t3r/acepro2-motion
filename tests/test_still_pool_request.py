import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_still_pool_request import requested_size


class StillPoolRequestTests(unittest.TestCase):
    def test_logged_4k_free_size(self):
        self.assertEqual(requested_size(0x0d13a380), 218342272)

    def test_small_input_wraps_in_fragment(self):
        self.assertEqual(requested_size(0x100000), 0)
        self.assertEqual(requested_size(0xfffff), 0xffffffff)
