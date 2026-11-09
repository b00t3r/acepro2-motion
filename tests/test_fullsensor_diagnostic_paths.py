import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_fullsensor_stream_layout import inspect
from livephoto_harness import ROOT, run_still_sensor_selection
from probe_fullsensor_resource import probe


class FullSensorDiagnosticPathsTests(unittest.TestCase):
    def test_later_narrow_mode_guard_does_not_overwrite_mode_53(self):
        image = (ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes()
        for narrow in (0, 1):
            with self.subTest(narrow=narrow):
                outcome = run_still_sensor_selection(narrow=narrow, sensor_mode=53,
                                                     image_data=image, livephoto=True)
                self.assertEqual(outcome['sensor_mode'], 53)

    def test_native_resource_routing_keeps_existing_16x9_unchanged(self):
        result = probe()
        for case in result['cases']:
            if case['resource'] == 226:
                self.assertEqual(case['before_ids'], case['after_ids'])
            else:
                self.assertEqual(case['after_ids'], [49, 49])
        self.assertEqual(result['selected_template']['template_index'], 42)
        self.assertEqual(result['template_frame_rate'], [5000, 1000])
        self.assertFalse(result['hardware_executed'])

    def test_template_does_not_silently_match_existing_stream_topology(self):
        self.assertNotEqual(inspect(42)['stream_count'], inspect(16)['stream_count'])


if __name__ == '__main__':
    unittest.main()
