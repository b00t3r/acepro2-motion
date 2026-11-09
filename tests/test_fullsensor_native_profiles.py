import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit_fullsensor_native_profiles import audit


class NativeFullSensorProfileTests(unittest.TestCase):
    def test_native_full_height_format_inventory(self):
        result=audit()
        rows=result['full_height_sensor_formats']
        self.assertEqual(result['total_formats_inspected'],60)
        self.assertEqual([r['format'] for r in rows],[42,43])
        self.assertTrue(all(r['sensor_mode']==53 and r['sensor_input_rate']==5 for r in rows))
        self.assertTrue(all('[M_RAW_0]' in r['vin_tree'] for r in rows))


if __name__=='__main__':unittest.main()
