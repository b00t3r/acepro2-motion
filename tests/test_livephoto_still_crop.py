"""Check the actual RawPiv FOV mismatch separately from JPEG metadata."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from livephoto_harness import run_rawpiv_fov_fragment
from inspect_zoom_ui import livephoto_disable_reason


class RawPivCropTests(unittest.TestCase):
    def test_stock_narrow_flag_does_not_change_rawpiv_fov_math(self):
        wide = run_rawpiv_fov_fragment(narrow=0)
        narrow = run_rawpiv_fov_fragment(narrow=1)
        self.assertEqual(wide['effective_fov_type'], 5)
        self.assertEqual(narrow['effective_fov_type'], 3)
        self.assertEqual(wide['fov_degrees'], narrow['fov_degrees'])
        self.assertAlmostEqual(narrow['fov_degrees'], 110)

    def test_effective_fov_edit_changes_narrow_math(self):
        narrow = run_rawpiv_fov_fragment(narrow=1, use_effective_fov=True)
        self.assertEqual(narrow['effective_fov_type'], 3)
        self.assertAlmostEqual(narrow['fov_degrees'], 63)

    def test_edit_preserves_unzoomed_fov_math(self):
        for fov in [1, 2, 3, 4, 5, 6]:
            with self.subTest(fov=fov):
                stock = run_rawpiv_fov_fragment(configured_fov=fov)
                edited = run_rawpiv_fov_fragment(configured_fov=fov, use_effective_fov=True)
                self.assertEqual(stock['fov_degrees'], edited['fov_degrees'])
                self.assertEqual(stock['distance'], edited['distance'])


class InverseUiTests(unittest.TestCase):
    def test_stock_disables_livephoto_with_either_zoom_route(self):
        for args in [{'narrow': 1}, {'ratio': 2.0}]:
            result = livephoto_disable_reason(refresh_control=True, press_button=True, **args)
            self.assertEqual(result['reason'], 4)
            self.assertEqual(result['disabled_flag'], 1)
            self.assertEqual(result['press_outcome'], 'warning_resource_boundary')

    def test_edit_allows_both_zoom_routes_and_real_button(self):
        for args in [{'narrow': 1}, {'ratio': 2.0}, {}]:
            result = livephoto_disable_reason(bypass_zoom_restriction=True,
                                             refresh_control=True, press_button=True, **args)
            self.assertEqual(result['reason'], 0)
            self.assertEqual(result['disabled_flag'], 0)
            self.assertEqual(result['press_outcome'], 'livephoto_switch_request_boundary')

    def test_edit_retains_other_guards_and_nonphoto_mode_behavior(self):
        for args, expected in [({'capability_value': 5, 'narrow': 1}, 17),
                               ({'error_status': 1, 'narrow': 1}, 15),
                               ({'selected_mode': 2, 'narrow': 1}, 4),
                               ({'selected_mode': 2, 'ratio': 2.0}, 4)]:
            result = livephoto_disable_reason(bypass_zoom_restriction=True,
                                             refresh_control=True, **args)
            self.assertEqual(result['reason'], expected)
            self.assertEqual(result['disabled_flag'], 1)
