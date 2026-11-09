import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_timelapse_effect import probe


class TimelapseEffectTests(unittest.TestCase):
    def test_selector_enforces_minimum_when_setter_runs(self):
        for selector in (0, 1):
            for requested in (0, 2, 5, 6):
                result = probe(selector, requested, 1)
                self.assertEqual(result['stored_interval'], max(requested, 5) if selector else requested)
                self.assertEqual(result['stored_short_rec'], 1)


if __name__ == '__main__':
    unittest.main()
