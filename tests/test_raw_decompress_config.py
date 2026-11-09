import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_raw_decompress_config import probe


class RawDecompressConfigTests(unittest.TestCase):
    def test_source_mode_configuration(self):
        for mode in (3,7):
            result=probe(7680,4320,mode,0,7488,15360)
            self.assertEqual(result['status'],0)
            self.assertEqual(result['stored_modes'],[mode,0])
            self.assertEqual(result['work_mode'],1)
            self.assertFalse(result['hardware_executed'])

    def test_invalid_dimensions_and_double_compression(self):
        self.assertEqual(probe(0,4320,3,0,7488,15360)['status'],1)
        self.assertEqual(probe(7680,4320,3,7,7488,15360)['status'],1)


if __name__=='__main__':
    unittest.main()
