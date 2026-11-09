import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_rawpiv_buffer_guard import probe


class RawPivGuardTests(unittest.TestCase):
    def test_boundary(self):
        for raw,aux,height in ((8192,2048,3072),(15360,3840,4320)):
            required=(raw+aux)*height
            self.assertEqual(probe(raw,height,aux,height,required-1)['outcome'],'insufficient')
            self.assertEqual(probe(raw,height,aux,height,required)['outcome'],'sufficient')


if __name__=='__main__':
    unittest.main()
