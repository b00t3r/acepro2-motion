"""Check the actual firmware lookup that a menu-only resolution unlock would hit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_full_resolution import select_photo_resource


class FullResolutionAudit(unittest.TestCase):
    def test_full_resolution_has_normal_photo_resources(self):
        for resolution in (4, 5, 7):
            with self.subTest(resolution=resolution):
                result = select_photo_resource(resolution, 12)
                self.assertEqual(result['status'], 0)
                self.assertGreaterEqual(result['descriptor'][1], 8000)

    def test_live_photo_has_only_lower_resolution_resources(self):
        for resolution in (2, 3, 6):
            with self.subTest(resolution=resolution):
                result = select_photo_resource(resolution, 17)
                self.assertEqual(result['status'], 0)
                self.assertLessEqual(result['descriptor'][3], 4096)

    def test_full_resolution_live_photo_fails_resource_lookup(self):
        for resolution in (4, 5, 7):
            with self.subTest(resolution=resolution):
                result = select_photo_resource(resolution, 17)
                self.assertEqual(result['status'], 0xffff)
                self.assertEqual(result['resource_index'], 0xffffffff)
