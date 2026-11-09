import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_record_photo_support import probe


class RecordPhotoSupportTests(unittest.TestCase):
    def test_controlled_configuration_changes_result(self):
        self.assertEqual(probe(0,0,0)['returned'],0)
        self.assertEqual(probe(0,1,0)['returned'],0)
        self.assertEqual(probe(0,2,0)['returned'],1)
        self.assertEqual(probe(0,2,5)['returned'],0)
        self.assertEqual(probe(0,2,0,other_guard=1)['returned'],0)


if __name__=='__main__':
    unittest.main()
