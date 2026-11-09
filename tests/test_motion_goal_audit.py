import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_motion_goal import audit


class MotionGoalAuditTests(unittest.TestCase):
    def test_native_1080_profile_and_ordinary_still_gap(self):
        result=audit()
        profile=next(r for r in result['native_1080_high_streams'] if r['format']==26)
        self.assertEqual(profile['sensor_mode'],36)
        self.assertEqual(profile['streams'][0]['canvas'],[1920,1080])
        self.assertEqual(profile['streams'][0]['rate'],[30000,1001])
        capture=result['ordinary_full_resolution_capture']
        self.assertFalse(capture['livephoto_enabled'])
        self.assertEqual(capture['start_stop_to_preview_return_ticks'],922)
        self.assertEqual(len(capture['events']),5)


if __name__=='__main__': unittest.main()
