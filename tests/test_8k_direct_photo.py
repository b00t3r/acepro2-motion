import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_8k_direct_photo import audit


class Direct8KTests(unittest.TestCase):
    def test_callback_retains_controlled_sizes(self):
        result=audit()
        self.assertEqual(result['static_profile']['streams'][0]['canvas'],[7680,4320])
        self.assertEqual(result['static_profile']['sensor_rate_words'],[24000,1000])
        for case in result['experiments']:
            self.assertEqual(case['sensor_mode'],20)
            self.assertEqual(case['initial_raw_size'],case['final_raw_size'])
            self.assertFalse(case['hardware_executed'])


if __name__=='__main__':
    unittest.main()
