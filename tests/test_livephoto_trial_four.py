"""Replay the fourth trial's actual packaged bytes, without test-time edits."""
import functools
import hashlib
import sys
import unittest
from pathlib import Path

import lz4.frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package
from livephoto_harness import image, GateInputs, run_gate, run_livephoto_config, run_rawpiv_fov_fragment
from inspect_zoom_ui import livephoto_disable_reason, zoom_disable_reason


@functools.lru_cache(maxsize=1)
def candidate_image():
    path = ROOT / 'builds/offline-livephoto-still/Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin'
    data = path.read_bytes()
    expected = 'af1c7e5d8f3ae9450a4702f1e54f5850b7d3c8fc9771a34527a7d46912ef5f4a'
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Fourth-trial package changed')
    return lz4.frame.decompress(unpack_package(data)['parts'][0]['payload'])


class TrialFourPackageTests(unittest.TestCase):
    def test_exact_decoded_allowlist_and_usb_marker(self):
        expected = bytearray(image())
        for address, value in [(0x369ea4, '00e8427a'), (0x401540, '7f6e0079'),
                               (0x55adec, '0e000014'), (0x76c178, '81de40b9'),
                               (0x55b034, 'f3ffff17')]:
            expected[address - 0x50000:address - 0x50000 + 4] = bytes.fromhex(value)
        for offset in USB_OFFSETS:
            marker = b'Insta360 Ace Pro Y'
            expected[offset:offset + len(marker)] = marker
        self.assertTrue(candidate_image() == expected, 'Unexpected decoded firmware change')

    def test_packaged_rawpiv_fov_math_uses_narrow_override(self):
        for narrow, expected in [(0, 110), (1, 63)]:
            result = run_rawpiv_fov_fragment(narrow=narrow, image_data=candidate_image())
            self.assertAlmostEqual(result['fov_degrees'], expected)
        for fov in range(1, 7):
            stock = run_rawpiv_fov_fragment(configured_fov=fov)
            actual = run_rawpiv_fov_fragment(configured_fov=fov, image_data=candidate_image())
            self.assertEqual(actual['fov_degrees'], stock['fov_degrees'])
            self.assertEqual(actual['distance'], stock['distance'])

    def test_packaged_inverse_ui_guard_and_button(self):
        for args in [{'narrow': 1}, {'ratio': 2.0}, {}]:
            actual = livephoto_disable_reason(refresh_control=True, press_button=True,
                                             image_data=candidate_image(), **args)
            self.assertEqual(actual['reason'], 0)
            self.assertEqual(actual['disabled_flag'], 0)
            self.assertEqual(actual['press_outcome'], 'livephoto_switch_request_boundary')
        for args, expected in [({'capability_value': 5}, 17), ({'error_status': 2}, 15),
                               ({'selected_mode': 2, 'narrow': 1}, 4)]:
            actual = livephoto_disable_reason(refresh_control=True, image_data=candidate_image(), **args)
            self.assertEqual(actual['reason'], expected)
            self.assertEqual(actual['disabled_flag'], 1)

    def test_packaged_zoom_widget_guards_both_states_and_all_warning_paths(self):
        for state in [1, 2]:
            for entry in [0x5beb40, 0x5b7660, 0x555100]:
                actual = zoom_disable_reason(state, refresh_control=True, press_button=True,
                                             press_entry=entry, image_data=candidate_image())
                self.assertEqual(actual['reason'], 0)
                self.assertEqual(actual['availability_flag'], 1)
                self.assertEqual(actual['press_outcome'], 'next_ui_action_boundary')
            for args, reason in [({'guard_a': 1}, 7), ({'guard_b': 1}, 11),
                                  ({'feature_available': False}, 4), ({'lens_value': 4}, 19)]:
                actual = zoom_disable_reason(state, refresh_control=True,
                                             image_data=candidate_image(), **args)
                self.assertEqual(actual['reason'], reason)
                self.assertEqual(actual['availability_flag'], 0)

    def test_packaged_real_support_check_bridge_and_capture_config(self):
        args = GateInputs(livephoto=True, capture_type_value=1, capture_mode_value=12,
                          actual_capture_mode_value=17)
        actual = run_gate(args, image_data=candidate_image(), via_gui_bridge=True,
                          execute_support_check=True, through_config_write=True)
        self.assertEqual(actual['requested_config'], {'narrow': 1, 'ratio_percent': 100})
        for narrow in [0, 1]:
            config = run_livephoto_config(226, narrow=narrow, image_data=candidate_image())
            self.assertEqual(config['narrow_flag'], narrow)
            self.assertEqual(config['adjacent_crop_field'], 0)
            self.assertEqual(config['resource_ids'], [31, 31])
            self.assertEqual(config['livephoto_flag'], 1)
