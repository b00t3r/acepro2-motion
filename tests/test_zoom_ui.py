import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_zoom_ui import warning_resource, zoom_disable_reason


class ZoomUITests(unittest.TestCase):
    def test_full_refresh_remains_blocked_in_state_two_with_first_edit(self):
        result = zoom_disable_reason(2, allow_model_state_one=True, refresh_control=True)
        self.assertEqual(result, {'reason': 16, 'availability_flag': 0, 'model_state_after': 2})

    def test_full_refresh_with_both_state_edit(self):
        for state in [0, 1, 2]:
            with self.subTest(state=state):
                result = zoom_disable_reason(state, allow_both_model_states=True, refresh_control=True)
                self.assertEqual(result, {'reason': 0, 'availability_flag': 1, 'model_state_after': state})

    def test_both_state_edit_retains_other_reasons(self):
        for state in [1, 2]:
            for args, reason in [({'guard_a': 1}, 7), ({'guard_b': 1}, 11),
                                  ({'feature_available': False}, 4), ({'lens_value': 4}, 19)]:
                with self.subTest(state=state, args=args):
                    result = zoom_disable_reason(state, allow_both_model_states=True,
                                                 refresh_control=True, **args)
                    self.assertEqual(result['reason'], reason)
                    self.assertEqual(result['availability_flag'], 0)

    def test_warning_resource_names_live_photo_and_zoom(self):
        text = warning_resource()
        self.assertIn('Live Photo', text)
        self.assertIn('变^焦', text)

    def test_stock_reason_16_for_both_ui_states(self):
        for state in [1, 2]:
            self.assertEqual(zoom_disable_reason(state), 16)
        self.assertEqual(zoom_disable_reason(0), 0)

    def test_edit_allows_only_ui_state_one(self):
        self.assertEqual(zoom_disable_reason(1, allow_model_state_one=True), 0)
        self.assertEqual(zoom_disable_reason(2, allow_model_state_one=True), 16)

    def test_other_guards_remain(self):
        for args, expected in [({'guard_a': 1}, 7), ({'guard_b': 1}, 11),
                               ({'feature_available': False}, 4), ({'lens_value': 4}, 19)]:
            with self.subTest(args=args):
                self.assertEqual(zoom_disable_reason(allow_model_state_one=True, **args), expected)

    def test_other_selected_modes_unchanged(self):
        for state in [0, 1, 2]:
            for selected in [0, 1, 2, 4]:
                args = {'model_state': state, 'selected_mode': selected}
                self.assertEqual(zoom_disable_reason(**args),
                                 zoom_disable_reason(allow_model_state_one=True, **args))


if __name__ == '__main__':
    unittest.main()
