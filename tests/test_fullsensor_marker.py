import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_fullsensor_marker import run


class FullSensorMarkerTests(unittest.TestCase):
    def test_marker_success_and_failure_cases(self):
        yes = run(227, 1, True)
        self.assertTrue(yes['enabled'])
        self.assertEqual(yes['calls'][0], ['open', 'C:\\FULLSENSOR.ENABLE', 'rb'])
        self.assertEqual(yes['calls'][1][0], 'close')
        self.assertFalse(run(227, 1, False)['enabled'])
        self.assertFalse(run(227, 1, True, close_ok=False)['enabled'])
        self.assertFalse(run(227, 1, True, null_handle=True)['enabled'])

    def test_other_modes_do_not_touch_filesystem(self):
        for resource, narrow in ((227, 0), (226, 1)):
            result = run(resource, narrow, True)
            self.assertFalse(result['enabled'])
            self.assertEqual(result['calls'], [])


if __name__ == '__main__':
    unittest.main()
