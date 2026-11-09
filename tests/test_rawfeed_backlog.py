import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_rawfeed_backlog import probe


class BacklogTests(unittest.TestCase):
    def test_threshold_follows_selector(self):
        for flag, limit in ((0,30),(1,3)):
            self.assertEqual(probe(flag,limit)['outcome'],'within_threshold')
            self.assertEqual(probe(flag,limit+1)['outcome'],'difference_exceeded')


if __name__=='__main__':
    unittest.main()
