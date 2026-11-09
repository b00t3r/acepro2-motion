import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import lz4.frame
from build_fullsensor_diagnostic import SOURCE, SOURCE_SHA, DEST, MARKER, patched_image
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from probe_guarded_fullsensor import BASE, HOOK, STUB, payload
from livephoto_geometry_patch import branch
from livephoto_harness import run_livephoto_config


class FullSensorDiagnosticBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = unpack_package(SOURCE.read_bytes())
        cls.candidate = unpack_package(DEST.read_bytes())
        cls.before = lz4.frame.decompress(cls.source['parts'][0]['payload'])
        cls.after = lz4.frame.decompress(cls.candidate['parts'][0]['payload'])

    def test_source_roundtrip_and_other_partitions(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        self.assertEqual(len(DEST.read_bytes()), len(SOURCE.read_bytes()))
        self.assertEqual(self.source['parts'][1:], self.candidate['parts'][1:])
        self.assertEqual(self.after, patched_image(self.before))

    def test_only_expected_image_bytes_change(self):
        expected = bytearray(self.before)
        expected[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
        expected[STUB-BASE:STUB-BASE+len(payload())] = payload()
        for at in USB_OFFSETS:
            expected[at:at+18] = MARKER
        self.assertEqual(self.after, bytes(expected))

    def test_live_photo_configuration_scope(self):
        for resource, narrow, expected in ((227, 1, [49, 49]), (227, 0, [30, 30]),
                                            (226, 1, [31, 31])):
            cfg = run_livephoto_config(resource, narrow, image_data=self.after, include_encoding=True)
            self.assertEqual(cfg['resource_ids'], expected)


if __name__ == '__main__':
    unittest.main()
