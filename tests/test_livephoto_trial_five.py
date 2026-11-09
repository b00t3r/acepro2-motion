"""Validate the packaged correction against failures observed in camera logs."""
import functools
import hashlib
import sys
import unittest
from pathlib import Path

import lz4.frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package
from livephoto_harness import (image, GateInputs, run_gate, run_livephoto_config,
    run_still_geometry_fragment, run_livephoto_enable_validation_fragment,
    run_livephoto_support_check)
from inspect_zoom_ui import livephoto_disable_reason, zoom_disable_reason


@functools.lru_cache(maxsize=1)
def candidate_image():
    path = ROOT / 'builds/offline-livephoto-pixels/Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin'
    data = path.read_bytes()
    expected = 'fd99de19dc472247d8e32521e8a7717c1989cfd7413bab18858b375a4572ad84'
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Fifth-trial package changed')
    return lz4.frame.decompress(unpack_package(data)['parts'][0]['payload'])


class TrialFivePackageTests(unittest.TestCase):
    def test_exact_decoded_allowlist_and_reverted_trial_y_math_edit(self):
        expected = bytearray(image())
        patches = [(0x369ea4, '00e8427a'), (0x401540, '7f6e0079'),
                   (0x55adec, '0e000014'), (0x55b034, 'f3ffff17'),
                   (0x362780, '39008052'), (0x37065c, '1f2003d5'),
                   (0x760840, '801b0154'),
                   (0x762bb0, '69f60890290549b969e4fe3566f9ff17')]
        for address, hex_data in patches:
            data = bytes.fromhex(hex_data)
            expected[address - 0x50000:address - 0x50000 + len(data)] = data
        for offset in USB_OFFSETS:
            expected[offset:offset + 18] = b'Insta360 Ace Pro V'
        self.assertTrue(candidate_image() == expected, 'Unexpected decoded firmware change')
        self.assertEqual(candidate_image()[0x76c178 - 0x50000:0x76c17c - 0x50000],
                         image()[0x76c178 - 0x50000:0x76c17c - 0x50000])

    def test_packaged_still_geometry_matches_wide_input_with_narrow_output(self):
        for live_flag in [1, 2, 3, 4]:
            actual = run_still_geometry_fragment(livephoto=live_flag, image_data=candidate_image())
            self.assertEqual(actual['projection_canvas'], [8192, 6144])
            self.assertEqual(actual['raw_dimensions'], [4096, 3072])
            self.assertEqual(actual['fov_type'], 3)
        for livephoto in [False, True]:
            for fov in [1, 2, 3, 4, 5, 6]:
                if livephoto and fov == 3:
                    continue
                self.assertEqual(run_still_geometry_fragment(livephoto, fov),
                                 run_still_geometry_fragment(livephoto, fov, image_data=candidate_image()))

    def test_packaged_enable_reaches_write_without_clearing_zoom(self):
        for narrow in [0, 1]:
            actual = run_livephoto_enable_validation_fragment(narrow=narrow, image_data=candidate_image())
            self.assertEqual(actual['narrow_clear_attempts'], 0)
            self.assertEqual(actual['outcome'], 'livephoto_enable_write_requested')
            self.assertEqual(actual['livephoto_enable_value'], 1)

    def test_packaged_support_check_retains_other_capabilities(self):
        for args in [{'factory_mode': 1}, {'factory_mode': 3}, {'origin_mode': 17},
                     {'origin_mode': 0}, {'photo_resolution_id': 0}, {'photo_resolution_id': 4}]:
            self.assertFalse(run_livephoto_support_check(narrow=1, image_data=candidate_image(),
                             **args)['supported'])

    def test_packaged_inverse_button_and_guards(self):
        for args in [{'narrow': 1}, {'ratio': 2.0}, {}]:
            actual = livephoto_disable_reason(refresh_control=True, press_button=True,
                                             image_data=candidate_image(), **args)
            self.assertEqual(actual['disabled_flag'], 0)
            self.assertEqual(actual['press_outcome'], 'livephoto_switch_request_boundary')
        for args, reason in [({'capability_value': 5}, 17), ({'error_status': 2}, 15),
                              ({'selected_mode': 2, 'narrow': 1}, 4)]:
            self.assertEqual(livephoto_disable_reason(image_data=candidate_image(), **args)['reason'], reason)

    def test_packaged_zoom_ui_both_states_and_other_guards(self):
        for state in [1, 2]:
            for entry in [0x5beb40, 0x5b7660, 0x555100]:
                actual = zoom_disable_reason(state, refresh_control=True, press_button=True,
                                             press_entry=entry, image_data=candidate_image())
                self.assertEqual(actual['availability_flag'], 1)
                self.assertEqual(actual['press_outcome'], 'next_ui_action_boundary')
            for args, reason in [({'guard_a': 1}, 7), ({'guard_b': 1}, 11),
                                  ({'feature_available': False}, 4), ({'lens_value': 4}, 19)]:
                self.assertEqual(zoom_disable_reason(state, refresh_control=True,
                                 image_data=candidate_image(), **args)['reason'], reason)

    def test_packaged_native_bridge_and_capture_config_preserve_zoom(self):
        args = GateInputs(livephoto=True, capture_type_value=1, capture_mode_value=12,
                          actual_capture_mode_value=17)
        result = run_gate(args, image_data=candidate_image(), via_gui_bridge=True,
                          execute_support_check=True, through_config_write=True)
        self.assertEqual(result['requested_config'], {'narrow': 1, 'ratio_percent': 100})
        config = run_livephoto_config(226, narrow=1, image_data=candidate_image())
        self.assertEqual(config['narrow_flag'], 1)
        self.assertEqual(config['resource_ids'], [31, 31])
        self.assertEqual(config['livephoto_flag'], 1)
