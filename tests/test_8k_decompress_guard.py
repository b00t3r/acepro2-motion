import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_8k_decompress_guard import probe


class DecompressGuardTests(unittest.TestCase):
    def test_mode_and_size_boundaries(self):
        h,src,dst=4320,7488,15360
        self.assertEqual(probe(h,src,src*h,dst,dst*h,3)['outcome'],'passed_guard')
        self.assertEqual(probe(h,src,src*h-1,dst,dst*h,3)['outcome'],'source_too_small')
        self.assertEqual(probe(h,src,src*h,dst,dst*h-1,3)['outcome'],'destination_too_small')
        self.assertEqual(probe(h,src,src*h,dst,dst*h,9)['outcome'],'unsupported_mode')


if __name__=='__main__':
    unittest.main()
