import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_still_output_geometry import probe


class StillOutputGeometryProbeTests(unittest.TestCase):
    def test_enabled_output_uses_the_requested_dimensions(self):
        result = probe()
        self.assertEqual(result['native_structure_pairs'],
                         [[1, 5120], [1, 3840], [1, 5120], [1, 3840]])
        self.assertFalse(result['pixels_or_encoder_validated'])

    def test_disabled_output_uses_the_raw_frame_dimensions(self):
        result = probe(scale=0)
        self.assertEqual(result['native_structure_pairs'],
                         [[1, 8192], [1, 6144], [1, 8192], [1, 6144]])

    def test_native_baseline_crop_dimensions(self):
        for raw, output in (((8192, 6144), (8192, 4608)),
                            ((4096, 3072), (4096, 2304))):
            with self.subTest(raw=raw):
                result = probe(*raw, *output, 2)
                self.assertEqual([p[1] for p in result['native_structure_pairs']],
                                 [output[0], output[1], output[0], output[1]])


if __name__ == '__main__':
    unittest.main()
