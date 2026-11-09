"""Validate the exact third-trial package, without injecting test edits."""
import functools
import hashlib
import sys
import unittest
from pathlib import Path

import lz4.frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_usb_name_candidate import ROOT, unpack_package, USB_OFFSETS
from livephoto_harness import image, GateInputs, run_gate, run_livephoto_config
from inspect_zoom_ui import zoom_disable_reason


@functools.lru_cache(maxsize=1)
def candidate_image():
    path = ROOT / 'builds/offline-livephoto-ui-both/Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin'
    data = path.read_bytes()
    expected = 'c2b7b3d80962d21dbc637c1d43a9d2ce4105fc20946285e1acf81208c8d986bf'
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Third-trial package changed')
    return lz4.frame.decompress(unpack_package(data)['parts'][0]['payload'])


class TrialThreePackageTests(unittest.TestCase):
    def test_exact_decoded_changes_and_marker(self):
        expected = bytearray(image())
        for address, value in [(0x369ea4, '00e8427a'), (0x401540, '7f6e0079'),
                                (0x55adec, '0e000014')]:
            expected[address - 0x50000:address - 0x50000 + 4] = bytes.fromhex(value)
        for offset in USB_OFFSETS:
            marker = b'Insta360 Ace Pro Z'
            self.assertEqual(len(marker), len(b'Insta360 Ace Pro 2'))
            expected[offset:offset + len(marker)] = marker
        self.assertTrue(candidate_image() == expected, 'Unexpected decoded firmware change')
        # Earlier state-one-only edit is reverted by building from stock.
        self.assertEqual(candidate_image()[0x55ae20 - 0x50000:0x55ae24 - 0x50000],
                         bytes.fromhex('40feff54'))

    def test_both_states_all_warning_paths_in_packaged_binary(self):
        for state in [1, 2]:
            for entry in [0x5beb40, 0x5b7660, 0x555100]:
                with self.subTest(state=state, entry=hex(entry)):
                    result = zoom_disable_reason(state, image_data=candidate_image(),
                                                 refresh_control=True, press_button=True,
                                                 press_entry=entry)
                    self.assertEqual(result['reason'], 0)
                    self.assertEqual(result['availability_flag'], 1)
                    self.assertEqual(result['model_state_after'], state)
                    self.assertEqual(result['press_outcome'], 'next_ui_action_boundary')

    def test_unrelated_ui_restrictions_retained_in_package(self):
        for state in [1, 2]:
            for args, reason in [({'guard_a': 1}, 7), ({'guard_b': 1}, 11),
                                  ({'feature_available': False}, 4), ({'lens_value': 4}, 19)]:
                with self.subTest(state=state, args=args):
                    result = zoom_disable_reason(state, image_data=candidate_image(),
                                                 refresh_control=True, **args)
                    self.assertEqual(result['reason'], reason)
                    self.assertEqual(result['availability_flag'], 0)

    def test_packaged_app_bridge_and_real_support_check_request_narrow(self):
        args = GateInputs(livephoto=True, capture_type_value=1, capture_mode_value=12,
                          actual_capture_mode_value=17)
        result = run_gate(args, image_data=candidate_image(), via_gui_bridge=True,
                          execute_support_check=True, through_config_write=True)
        self.assertEqual(result['outcome'], 'zoom_config_write_requested')
        self.assertEqual(result['requested_config'], {'narrow': 1, 'ratio_percent': 100})

    def test_packaged_normalizer_preserves_narrow_and_livephoto_resource(self):
        result = run_livephoto_config(226, narrow=1, image_data=candidate_image())
        self.assertEqual(result['narrow_flag'], 1)
        self.assertEqual(result['adjacent_crop_field'], 0)
        self.assertEqual(result['resource_ids'], [31, 31])
        self.assertEqual(result['livephoto_flag'], 1)


if __name__ == '__main__':
    unittest.main()
