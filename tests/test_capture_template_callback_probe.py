import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_capture_template_callback import probe
from probe_fullsensor_actual_callback import probe as trace


class CaptureTemplateCallbackProbeTests(unittest.TestCase):
    def test_full_sensor_template_does_not_use_burst_raw_callback(self):
        full, burst, live = probe(49), probe(48), probe(30)
        self.assertEqual(full['callback'], '0x295ea0')
        self.assertEqual(live['callback'], '0x295ea0')
        self.assertEqual(burst['callback'], '0x287a80')
        self.assertFalse(full['callback_executed'])
        self.assertFalse(full['hardware_executed'])

    def test_full_template_reaches_delegate_with_full_geometry_in_controlled_trace(self):
        current, full = trace(16, 30), trace(42, 49)
        self.assertEqual(current['observed_at_delegated_callback']['sensor_mode'], 36)
        self.assertEqual(full['observed_at_delegated_callback'],
                         {'sensor_mode': 53, 'capture_mode': 53, 'raw_size': [8192, 6144]})
        self.assertTrue(full['delegated_callback_mocked'])
        self.assertFalse(full['complete_configuration_validated'])

    def test_controlled_delegate_preserves_full_geometry_for_each_zoom_setting(self):
        for narrow in (0, 1):
            with self.subTest(narrow=narrow):
                result = trace(42, 49, through_delegate=True, narrow=narrow)
                self.assertEqual(result['outcome'], 'delegate_returned')
                self.assertEqual(result['delegated_status'], 0)
                self.assertEqual(result['observed_at_delegated_callback'],
                                 {'sensor_mode': 53, 'capture_mode': 53, 'raw_size': [8192, 6144]})
                self.assertFalse(result['complete_configuration_validated'])


if __name__ == '__main__':
    unittest.main()
