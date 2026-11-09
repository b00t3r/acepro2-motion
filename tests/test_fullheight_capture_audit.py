import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_fullheight_capture import native_pitch, plane_sizes, WORKING, logged_memory_overlap
from audit_capture_pipeline import pureshot_format
from audit_zoom_isp_selection import replay, TABLE_COUNT
from livephoto_harness import image, BASE
import struct


class FullHeightCaptureAudit(unittest.TestCase):
    def test_ordinary_photo_memory_cannot_be_reused_with_live_video_reservation(self):
        result = logged_memory_overlap()
        live, full = result['layouts']
        self.assertEqual(result['video']['base'], 0xd0525380)
        self.assertEqual(live['overlap_with_video_bytes'], 0)
        self.assertEqual(live['still_pool_bytes'], 0xa2e9200)
        self.assertEqual(full['base'], 0xe9f45c80)
        self.assertGreater(full['overlap_with_video_bytes'], 0)
        self.assertEqual(result['existing_full_still_path_minimum_bytes'], 201326592)
        self.assertGreater(result['shortfall_against_recorded_live_pool_bytes'], 0)

    def test_full_resolution_id_does_not_select_full_tuning_in_live_mode(self):
        working = WORKING.read_bytes()
        for still_type in (0, 1):
            low = replay(recording=0, narrow=0, face=0, image_data=working,
                         resolution=2, still_type=still_type, live_flag=1)
            high = replay(recording=0, narrow=0, face=0, image_data=working,
                          resolution=4, still_type=still_type, live_flag=1)
            self.assertEqual((low['row'], low['root']), (high['row'], high['root']))
            self.assertIn('livephoto', high['table'])

    def test_full_table_count_comes_from_native_registration(self):
        self.assertEqual(TABLE_COUNT, 621)
        self.assertEqual(struct.unpack_from('<I', image(), 0x118f614 - BASE)[0], 0x52804da3)

    def test_logged_full_resolution_isp_profile_is_reproduced(self):
        result = replay(recording=0, narrow=0, face=0, image_data=WORKING.read_bytes(),
                        sub_mode=12, resolution=5, hdr=1, lens=0)
        self.assertEqual(result['row'], 616)
        self.assertEqual(result['table'], 'g_isp_ik_table_normalshot_48M')

    def test_native_live_raw_allocation_matches_recorded_hardware(self):
        row = plane_sizes(4096, 3072)
        self.assertEqual((row['raw_bytes'], row['ce_bytes'], row['raw_plus_ce_bytes']),
                         (25165824, 6291456, 31457280))

    def test_native_full_raw_allocation_matches_recorded_hardware(self):
        row = plane_sizes(8192, 6144)
        self.assertEqual((row['raw_bytes'], row['ce_bytes'], row['raw_plus_ce_bytes']),
                         (100663296, 25165824, 125829120))
        self.assertEqual(row['full_size_yuv420_bytes'], 75497472)

    def test_pitch_query_rejects_unestablished_widths(self):
        for width in (0, -1, 16384):
            with self.assertRaises(ValueError):
                native_pitch(width)

    def test_working_colour_fix_keeps_full_resolution_format_branch(self):
        working = WORKING.read_bytes()
        low = pureshot_format(0, raw_width=4096, image_data=working, livephoto=True)
        high = pureshot_format(0, raw_width=8192, image_data=working, livephoto=True)
        self.assertEqual(low['qbc'], 0)
        self.assertEqual(high['qbc'], 1)
        self.assertFalse(high['model_executed'])


if __name__ == '__main__':
    unittest.main()
