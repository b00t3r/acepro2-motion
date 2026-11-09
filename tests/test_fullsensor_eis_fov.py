import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from probe_fullsensor_eis_fov import run, run_eis_setup


class FullSensorEisFovTests(unittest.TestCase):
    def test_native_template_lookup(self):
        live, full = run(16,30), run(42,49)
        self.assertEqual((live['main_fov_index'], live['sub_fov_index']), (0,1))
        self.assertEqual((full['main_fov_index'], full['sub_fov_index']), (1,-1))
        self.assertEqual(full['main_iq_word'], '0x80000100')
        self.assertEqual(full['descriptors'][1]['main_lookup_type'], '0x8000')
        self.assertEqual([x['sub_lookup_flags'] for x in full['descriptors']], ['0x20','0x20'])

    def test_native_eis_setup_keeps_fullsensor_fov_selection(self):
        enabled = run_eis_setup(42,49,False)
        disabled = run_eis_setup(42,49,True)
        self.assertEqual((enabled['main_fov_index'], enabled['sub_fov_index']), (1,-1))
        self.assertEqual((enabled['live_eis_byte'], enabled['fov1_iq']), (1,'0x80000100'))
        self.assertEqual((disabled['live_eis_byte'], disabled['fov1_iq']), (0,'0x80000000'))
        self.assertTrue(enabled['native_lookup_and_setup_executed'])


if __name__=='__main__': unittest.main()
