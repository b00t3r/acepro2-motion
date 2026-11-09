import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_ring_index import probe


class RingIndexTests(unittest.TestCase):
    def test_native_wraps_at_the_selected_count(self):
        for flag, count in ((0,32),(1,5)):
            for n in (0,4,5,31,32,65):
                self.assertEqual(probe(flag,n)['selected_slot'],n % count)


if __name__ == '__main__':
    unittest.main()
