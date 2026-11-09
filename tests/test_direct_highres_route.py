import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_direct_highres_route import audit


class DirectRouteTests(unittest.TestCase):
    def test_native_profiles_and_isolated_callbacks(self):
        result=audit()
        profiles={p['format']:p for p in result['registered_direct_high_width_profiles']}
        self.assertEqual(profiles[7]['sensor_size'],[8192,4608])
        self.assertEqual(profiles[7]['nominal_sensor_fps'],24)
        self.assertEqual(profiles[58]['source_rect'],[1728,1296,4736,3552])
        self.assertTrue(all(p['sensor_mode']!=16 for p in profiles.values()))
        for case in result['experimental_direct_live_callback']:
            self.assertEqual(case['observed_at_delegated_callback']['sensor_mode'],16)
            self.assertFalse(case['hardware_executed'])


if __name__=='__main__':
    unittest.main()
