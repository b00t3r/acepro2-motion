import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_livephoto_encoder_dispatch import dispatch, logged_start


class LivePhotoEncoderDispatchTests(unittest.TestCase):
    def test_saved_camera_log_starts_two_streams(self):
        self.assertEqual(logged_start()['mask'], 3)

    def test_both_streams_follow_same_native_branch(self):
        for index in (16, 42):
            self.assertEqual(dispatch(index, 3)['outcome'], 'normal_stream_branch')

    def test_second_stream_alone_follows_different_branch(self):
        self.assertEqual(dispatch(16, 2)['outcome'], 'other_mask_branch')
        self.assertEqual(dispatch(42, 2)['outcome'], 'network_or_blue_branch')


if __name__ == '__main__':
    unittest.main()
