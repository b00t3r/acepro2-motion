import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_custom_resolution_lookup import probe
from probe_custom_resolution_transition import probe as transition
from audit_zoom_isp_selection import replay


class CustomResolutionLookupProbeTests(unittest.TestCase):
    def test_existing_live_and_normal_photo_lookups_remain_unchanged(self):
        for mode, resolutions in ((17, (2, 3, 6)), (12, (2, 3, 4, 5, 6, 7))):
            for resolution in resolutions:
                with self.subTest(mode=mode, resolution=resolution):
                    before = probe(resolution, mode, False)
                    after = probe(resolution, mode, True)
                    self.assertEqual((before['status'], before['resource_index']),
                                     (after['status'], after['resource_index']))

    def test_custom_live_lookup_is_experimental_and_uses_existing_capture_resource(self):
        self.assertEqual(probe(8)['status'], 65535)
        custom = probe(8, custom=True)
        self.assertEqual((custom['status'], custom['resource_index']), (0, 194))
        self.assertFalse(custom['high_resolution_capture'])
        self.assertEqual(probe(8, actual_mode=12, custom=True)['status'], 65535)

    def test_unknown_resolution_is_written_before_lookup_rejects_it(self):
        result = transition(8)
        self.assertEqual(result['outcome'], 'resource_lookup_failed')
        self.assertEqual(result['resolution_after_write'], 8)
        self.assertEqual(transition(3)['outcome'], 'resource_lookup_succeeded')

    def test_custom_id_alone_does_not_select_a_new_image_processing_profile(self):
        for still_type in (0, 1):
            with self.subTest(still_type=still_type):
                args = dict(recording=0, narrow=0, face=0, still_type=still_type,
                            live_flag=1, sub_mode=17, hdr=1, lens=1)
                standard = replay(resolution=2, **args)
                custom = replay(resolution=8, **args)
                self.assertEqual((custom['row'], custom['table']),
                                 (standard['row'], standard['table']))


if __name__ == '__main__':
    unittest.main()
