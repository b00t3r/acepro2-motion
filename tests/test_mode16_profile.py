import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_mode16_profile import audit


class Mode16ProfileTests(unittest.TestCase):
    def test_controlled_callback_and_narrow_fragment(self):
        result=audit()
        for case in result['callback_cases']:
            self.assertEqual(case['observed_at_delegated_callback'],
                {'sensor_mode':16,'capture_mode':16,'raw_size':[8192,6144]})
            self.assertTrue(case['frame_lookup_mocked'])
            self.assertFalse(case['complete_configuration_validated'])
        self.assertEqual([x['sensor_mode'] for x in result['later_narrow_fragment']],[16,16])


if __name__=='__main__': unittest.main()
