import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_mode16_topology import audit


class Mode16TopologyTests(unittest.TestCase):
    def test_unregistered_mode_and_three_view_reference(self):
        result=audit()
        self.assertEqual(result['registered_profiles_using_mode16'],[])
        p=next(v for v in result['profiles'] if v['format']==31)
        self.assertEqual(p['sensor_mode'],3)
        self.assertIn('[FOV_0][FOV_1_BYPASS][M_RAW_0][FOV_2]',p['vin_tree'])
        self.assertEqual(len(p['fovs']),3)
        self.assertEqual(len(p['streams']),4)
        self.assertFalse(result['firmware_candidate_created'])


if __name__=='__main__': unittest.main()
