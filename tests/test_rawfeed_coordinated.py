import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawfeed_buffer_sizing import probe as sizing
from probe_rawfeed_ring_index import probe as ring


class CoordinatedFragmentTests(unittest.TestCase):
    def test_sizing_and_index_experiment_agree(self):
        layout=sizing(8192,6144,0,force_five=True)
        for counter in range(40):
            result=ring(0,counter,force_five=True)
            self.assertEqual(result['selected_slot'],counter % 5)
            self.assertLessEqual(result['offset_bytes'] + result['frame_bytes'], layout['raw_total_bytes'])


if __name__=='__main__':
    unittest.main()
