import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_device_motion_photo import check


class MotionPhotoValidationTests(unittest.TestCase):
    def test_captures_and_corruption(self):
        root=Path(__file__).resolve().parents[1]/'analysis/gallery-bitrate-trial-q-hardware'
        for stem in ('LIV_20261029_152411_936','LIV_20261029_152417_937'):
            jpg=(root/(stem+'.jpg')).read_bytes()
            lrv=(root/(stem+'.lrv')).read_bytes()
            mp=(root/(stem+'.MP.jpg')).read_bytes()
            self.assertTrue(check(jpg,lrv,mp)['video_exact_match'])
            damaged=bytearray(mp);damaged[-1]^=1
            with self.assertRaises(ValueError): check(jpg,lrv,damaged)
