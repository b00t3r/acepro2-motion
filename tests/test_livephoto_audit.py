"""Replay the actual second-trial binary, including known failing paths.

These controlled-state checks deliberately do not assert the camera's internal
state values. They test previously omitted branches and expose mock boundaries.
"""
import functools
import hashlib
import sys
import unittest
from pathlib import Path

import lz4.frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_usb_name_candidate import unpack_package
from livephoto_harness import ROOT, GateInputs, run_gate, run_livephoto_mode_switch_fragment
from inspect_zoom_ui import zoom_disable_reason, warning_resource, zoom_toggle_notification


@functools.lru_cache(maxsize=1)
def trial_two_image():
    data = (ROOT / 'builds/offline-livephoto-ui/Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin').read_bytes()
    expected = '3afd9ac1674464d8ebf3b75b3129e135941a2c00c4debdba06644c0655b01b13'
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Second hardware-trial candidate changed')
    return lz4.frame.decompress(unpack_package(data)['parts'][0]['payload'])


class ReleasedCandidateAudit(unittest.TestCase):
    def test_released_binary_still_disables_zoom_in_state_two(self):
        data = trial_two_image()
        for state, reason, flag in [(0, 0, 1), (1, 0, 1), (2, 16, 0)]:
            with self.subTest(state=state):
                actual = zoom_disable_reason(state, refresh_control=True, image_data=data)
                self.assertEqual(actual['reason'], reason)
                self.assertEqual(actual['availability_flag'], flag)

    def test_warning_default_language_matches_user_report(self):
        text = warning_resource(language=0)
        # Embedded Wizard embeds font line-breaking markers in the resource.
        text = text.replace('~', '').replace('^', '')
        self.assertIn('Live Photo', text)
        self.assertIn('zoom', text.lower())
        self.assertEqual(text, 'Zoom is not supported when Live Photo is enabled/switched')

    def test_released_widget_press_reaches_the_reported_warning(self):
        for entry in [0x5beb40, 0x5b7660, 0x555100]:
            with self.subTest(entry=hex(entry)):
                result = zoom_disable_reason(2, refresh_control=True, press_button=True,
                                             press_entry=entry, image_data=trial_two_image())
                self.assertEqual(result['press_outcome'], 'warning_resource_requested')
                self.assertEqual(result['warning_resource'], 0x19c4d40)

    def test_both_state_edit_passes_widget_warning_but_stops_before_app_action(self):
        for state in [1, 2]:
            for entry in [0x5beb40, 0x5b7660, 0x555100]:
                with self.subTest(state=state, entry=hex(entry)):
                    result = zoom_disable_reason(state, refresh_control=True, press_button=True,
                                                 press_entry=entry, allow_both_model_states=True)
                    self.assertEqual(result['press_outcome'], 'next_ui_action_boundary')
                    self.assertNotIn('warning_resource', result)

    def test_confusing_actual_and_origin_mode_reproduces_later_rejection(self):
        # 17 belongs in ActualMode after this camera's enable path; placing it
        # in OriginMode changes the real support decision.
        args = GateInputs(livephoto=True, capture_type_value=1, capture_mode_value=17,
                          actual_capture_mode_value=17)
        data = trial_two_image()
        first = run_gate(args, image_data=data, execute_support_check=True)
        self.assertEqual(first['outcome'], 'accepted_by_gate')
        continued = run_gate(args, image_data=data, execute_support_check=True,
                             through_config_write=True)
        self.assertEqual(continued['outcome'], 'rejected_by_support_check')
        self.assertNotIn('requested_config', continued)

    def test_livephoto_enable_preserves_normal_origin_and_sets_actual_mode(self):
        self.assertEqual(run_livephoto_mode_switch_fragment(),
                         {'mode': 1, 'submode': 0, 'origin_mode': 12, 'actual_mode': 17,
                          'preset_type': 0, 'preset_offset': 0})

    def test_switch_output_reaches_real_zoom_config_write_boundary(self):
        mode = run_livephoto_mode_switch_fragment()
        args = GateInputs(livephoto=True, capture_type_value=mode['mode'],
                          capture_submode_value=mode['submode'],
                          capture_mode_value=mode['origin_mode'],
                          actual_capture_mode_value=mode['actual_mode'])
        result = run_gate(args, image_data=trial_two_image(), execute_support_check=True,
                          through_config_write=True)
        self.assertEqual(result['outcome'], 'zoom_config_write_requested')
        self.assertEqual(result['requested_config'], {'narrow': 1, 'ratio_percent': 100})

    def test_native_toggle_notification_chains_through_real_app_bridge(self):
        events = zoom_toggle_notification(current_narrow=0, supported_option_count=2)
        self.assertEqual(events, [{'device_id': 0xd9, 'narrow': 1}])
        mode = run_livephoto_mode_switch_fragment()
        args = GateInputs(livephoto=True, capture_type_value=mode['mode'],
                          capture_submode_value=mode['submode'],
                          capture_mode_value=mode['origin_mode'],
                          actual_capture_mode_value=mode['actual_mode'],
                          requested_narrow=events[0]['narrow'])
        result = run_gate(args, image_data=trial_two_image(), execute_support_check=True,
                          through_config_write=True, via_gui_bridge=True)
        self.assertEqual(result['outcome'], 'zoom_config_write_requested')
        self.assertEqual(result['requested_config'], {'narrow': 1, 'ratio_percent': 100})
        self.assertTrue(result['gui_bridge_executed'])


if __name__ == '__main__':
    unittest.main()
