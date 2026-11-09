"""Reproduce the logged canvas mismatch and enable failure in native code."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from livephoto_harness import run_still_geometry_fragment, run_livephoto_enable_validation_fragment
from test_livephoto_trial_four import candidate_image


class LoggedFailureTests(unittest.TestCase):
    def test_installed_y_reproduces_logged_still_canvas_halving(self):
        actual = run_still_geometry_fragment(livephoto=True, image_data=candidate_image())
        self.assertEqual(actual['calibration_canvas'], [8192, 6144])
        self.assertEqual(actual['projection_canvas'], [4096, 3072])
        self.assertEqual(actual['raw_dimensions'], [4096, 3072])

    def test_corrected_livephoto_keeps_wide_input_canvas_and_narrow_output_fov(self):
        actual = run_still_geometry_fragment(livephoto=True, corrected=True)
        self.assertEqual(actual['projection_canvas'], [8192, 6144])
        self.assertEqual(actual['raw_dimensions'], [4096, 3072])
        self.assertEqual(actual['fov_type'], 3)

    def test_regular_photo_narrow_and_other_fovs_unchanged(self):
        for livephoto in [False, True]:
            for fov in [1, 2, 3, 4, 5, 6]:
                if livephoto and fov == 3:
                    continue
                with self.subTest(livephoto=livephoto, fov=fov):
                    self.assertEqual(run_still_geometry_fragment(livephoto, fov),
                                     run_still_geometry_fragment(livephoto, fov, corrected=True))

    def test_installed_y_reproduces_backend_enable_failure(self):
        actual = run_livephoto_enable_validation_fragment(image_data=candidate_image())
        self.assertEqual(actual['narrow_clear_attempts'], 1)
        self.assertEqual(actual['outcome'], 'rejected_by_livephoto_support_check')

    def test_corrected_enable_requests_on_without_clearing_zoom(self):
        actual = run_livephoto_enable_validation_fragment(corrected=True)
        self.assertEqual(actual['narrow_clear_attempts'], 0)
        self.assertEqual(actual['livephoto_enable_value'], 1)
        self.assertEqual(actual['outcome'], 'livephoto_enable_write_requested')
