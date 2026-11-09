"""Reproduce the backend restriction missed by UI-boundary-only checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from livephoto_harness import run_livephoto_support_check
from test_livephoto_trial_four import candidate_image


class LivePhotoEnableAudit(unittest.TestCase):
    def test_installed_trial_y_still_rejects_zoom_in_backend(self):
        for photo_resolution_id in [2, 3, 6]:
            with self.subTest(photo_resolution_id=photo_resolution_id):
                self.assertTrue(run_livephoto_support_check(photo_resolution_id=photo_resolution_id,
                                image_data=candidate_image())['supported'])
                self.assertFalse(run_livephoto_support_check(narrow=1, photo_resolution_id=photo_resolution_id,
                                 image_data=candidate_image())['supported'])

    def test_memory_only_edit_accepts_zoom_with_supported_capture_modes(self):
        for origin in [12, 16]:
            for photo_resolution_id in [2, 3, 6]:
                self.assertTrue(run_livephoto_support_check(narrow=1, origin_mode=origin,
                                photo_resolution_id=photo_resolution_id, allow_zoom=True)['supported'])

    def test_memory_only_edit_retains_other_capability_checks(self):
        for args in [{'factory_mode': 1}, {'factory_mode': 3}, {'origin_mode': 17},
                     {'origin_mode': 0}, {'photo_resolution_id': 0}, {'photo_resolution_id': 1},
                     {'photo_resolution_id': 4}, {'photo_resolution_id': 5}]:
            with self.subTest(args=args):
                self.assertFalse(run_livephoto_support_check(narrow=1, allow_zoom=True,
                                 **args)['supported'])
