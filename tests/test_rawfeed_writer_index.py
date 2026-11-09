import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_rawfeed_writer_index import probe


class WriterIndexTests(unittest.TestCase):
    def test_native_and_experimental_wraps(self):
        for site in ('writer_a','writer_b'):
            for flag,force,count in ((0,False,32),(1,False,5),(0,True,5)):
                for counter in (0,4,5,31,32,65):
                    self.assertEqual(probe(site,flag,counter,force)['selected_slot'],counter % count)


if __name__=='__main__':
    unittest.main()
