import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from livephoto_harness import GateInputs, run_gate, run_zoom_forward, run_livephoto_config, ROOT
from livephoto_harness import run_video_zoom_gate, run_still_request_fragment
from livephoto_harness import run_profile_selection_fragment
from livephoto_harness import run_still_fov_selection, run_still_sensor_selection


class LivePhotoGateTests(unittest.TestCase):
    def test_candidate_gate_edit_preserves_other_rejections(self):
        edit = 'always_factory_compare'
        for livephoto in [False, True]:
            self.assertEqual(run_gate(GateInputs(livephoto=livephoto), edit)['outcome'], 'accepted_by_gate')
        for inputs in [GateInputs(livephoto=True, record_state=4),
                       GateInputs(livephoto=True, record_state=7),
                       GateInputs(livephoto=True, switch_busy=1),
                       GateInputs(livephoto=True, factory_mode_value=0),
                       GateInputs(livephoto=True, factory_mode_value=1),
                       GateInputs(livephoto=True, factory_mode_value=3)]:
            self.assertEqual(run_gate(inputs, edit)['outcome'], 'rejected_by_gate')

    def test_stock_allows_control_profile(self):
        self.assertEqual(run_gate()['outcome'], 'accepted_by_gate')

    def test_stock_rejects_livephoto(self):
        self.assertEqual(run_gate(GateInputs(livephoto=True))['outcome'], 'rejected_by_gate')

    def test_scalar_zoom_is_also_blocked_by_livephoto_gate(self):
        for enabled, outcome in [(False, 'accepted_by_gate'), (True, 'rejected_by_gate')]:
            with self.subTest(livephoto=enabled):
                inputs = GateInputs(livephoto=enabled, requested_narrow=-1, requested_ratio=2.0)
                self.assertEqual(run_gate(inputs)['outcome'], outcome)

    def test_memory_edit_changes_livephoto_decision(self):
        self.assertEqual(run_gate(GateInputs(livephoto=True), True)['outcome'], 'accepted_by_gate')

    def test_recording_state_checks_remain(self):
        for state in [4, 7]:
            with self.subTest(state=state):
                self.assertEqual(run_gate(GateInputs(livephoto=True, record_state=state), True)['outcome'],
                                 'rejected_by_gate')

    def test_busy_switch_check_remains(self):
        self.assertEqual(run_gate(GateInputs(livephoto=True, switch_busy=1), True)['outcome'],
                         'rejected_by_gate')

    def test_other_mode_value_check_remains(self):
        for value in [0, 1, 3]:
            with self.subTest(value=value):
                self.assertEqual(run_gate(GateInputs(livephoto=True, factory_mode_value=value), True)['outcome'],
                                 'rejected_by_gate')

    def test_stock_settings_have_separate_livephoto_restriction(self):
        config = json.loads((ROOT / 'analysis/extracted/camera_params.json').read_text())
        options = config['Iacwa586']['PHOTO_SINGLE']['undamage_zoom']['list']
        for resolution in ['4000_2250', '4096_3072']:
            self.assertIn('true', options[f'{resolution}|false|STANDARD'])
            self.assertEqual(options[f'{resolution}|true|STANDARD'], ['false'])


class ZoomForwardingTests(unittest.TestCase):
    def test_200_percent_reaches_service_as_2x(self):
        result = run_zoom_forward(200)
        self.assertEqual(result['service_ratios'], [2.0])
        self.assertEqual(result['notifications'], [{'event': 0x34, 'ratio': 2.0}])
        self.assertEqual(result['return_value'], 0)

    def test_explicit_ratio_uses_argument(self):
        self.assertEqual(run_zoom_forward(100, 2.0)['service_ratios'], [2.0])

    def test_1x_control(self):
        self.assertEqual(run_zoom_forward(100)['service_ratios'], [1.0])

    def test_notification_can_be_suppressed(self):
        result = run_zoom_forward(notify=False)
        self.assertEqual(result['service_ratios'], [2.0])
        self.assertEqual(result['notifications'], [])

    def test_service_error_propagates_without_success_notification(self):
        result = run_zoom_forward(setter_error=1)
        self.assertEqual(result['return_value'], 1)
        self.assertEqual(result['notifications'], [])


class LivePhotoConfigTests(unittest.TestCase):
    def test_dedicated_livephoto_resource(self):
        result = run_livephoto_config(226)
        self.assertEqual(result['resource_ids'], [31, 31])
        self.assertEqual(result['dimensions'], [3840, 2160])

    def test_preserve_edit_keeps_livephoto_resources_and_clears_adjacent_field(self):
        for narrow in [0, 1]:
            with self.subTest(narrow=narrow):
                result = run_livephoto_config(226, narrow, preserve_narrow=True)
                self.assertEqual(result['narrow_flag'], narrow)
                self.assertEqual(result['adjacent_crop_field'], 0)
                self.assertEqual(result['resource_ids'], [31, 31])
                self.assertEqual(result['livephoto_flag'], 1)

    def test_rewrite_clears_narrow_and_adjacent_crop_field(self):
        result = run_livephoto_config()
        self.assertEqual(result['livephoto_flag'], 1)
        self.assertEqual(result['narrow_flag'], 0)
        self.assertEqual(result['adjacent_crop_field'], 0)

    def test_rewrite_selects_equal_non_narrow_resource_ids(self):
        result = run_livephoto_config(21)
        self.assertEqual(result['resource_ids'], [18, 18])
        self.assertEqual(result['dimensions'], [3840, 2160])

    def test_4_by_3_resource_also_has_narrow_cleared(self):
        result = run_livephoto_config(178)
        self.assertEqual(result['narrow_flag'], 0)
        self.assertEqual(result['resource_ids'], [46, 46])
        self.assertEqual(result['dimensions'], [4096, 3072])

    def test_unzoomed_control_remains_unzoomed(self):
        self.assertEqual(run_livephoto_config(narrow=0)['narrow_flag'], 0)


class CapturePathTests(unittest.TestCase):
    def test_still_narrow_overrides_configured_fov(self):
        for configured_fov in [2, 4, 5]:
            self.assertEqual(run_still_fov_selection(1, configured_fov)['selected_fov'], 3)
            self.assertEqual(run_still_fov_selection(0, configured_fov)['selected_fov'], configured_fov)

    def test_still_narrow_changes_selected_sensor_modes(self):
        for mode in [3, 9, 36]:
            self.assertEqual(run_still_sensor_selection(1, mode)['sensor_mode'], 27)
        self.assertEqual(run_still_sensor_selection(1, 99)['sensor_mode'], 99)
        self.assertEqual(run_still_sensor_selection(0, 9)['sensor_mode'], 9)

    def test_capture_ids_select_metadata_rather_than_array_index(self):
        for capture_id, index, name in [(31, 15, 'HDR REC 4k'),
                                        (5, 2, 'ONLY HDR Liveview'),
                                        (202, 59, 'MRAW-FOV3-HDS-EIS')]:
            with self.subTest(capture_id=capture_id):
                result = run_profile_selection_fragment(capture_id)
                self.assertEqual(result['template_index'], index)
                self.assertIn(name, result['template_name'])

    def test_video_permission_with_feature_enabled_requires_narrow(self):
        self.assertFalse(run_video_zoom_gate(narrow=0)['allowed'])
        self.assertTrue(run_video_zoom_gate(narrow=1)['allowed'])

    def test_video_permission_without_feature_allows_both(self):
        for narrow in [0, 1]:
            self.assertTrue(run_video_zoom_gate(narrow, feature_8=False)['allowed'])

    def test_secondary_stream_resource_exclusions_remain(self):
        for resolution in [63, 64]:
            self.assertFalse(run_video_zoom_gate(1, stream=1, resolution_id=resolution)['allowed'])
        self.assertTrue(run_video_zoom_gate(1, stream=1)['allowed'])

    def test_starlapse_exclusion_remains(self):
        self.assertFalse(run_video_zoom_gate(1, capture_mode=0, capture_submode=20)['allowed'])

    def test_still_fragment_forwards_narrow_field(self):
        for narrow in [0, 1]:
            self.assertEqual(run_still_request_fragment(narrow)['request_narrow'], narrow)


if __name__ == '__main__':
    unittest.main()
