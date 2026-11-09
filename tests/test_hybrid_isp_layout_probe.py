import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from livephoto_harness import BASE, image
from probe_hybrid_isp_layout import ROOTS, prototype


class HybridISPLayoutProbeTests(unittest.TestCase):
    def test_preview_and_motion_tuning_match_the_original_live_table(self):
        data = image()
        for kind, (live, full) in ROOTS.items():
            with self.subTest(kind=kind):
                candidate, info = prototype(kind)
                # Root pointer, preview, and HDS occupy the first 55 words.
                self.assertEqual(candidate[:55 * 8], data[live-BASE:live-BASE+55*8])
                # The proposed still section comes from the native 48MP table.
                self.assertEqual(candidate[55*8:82*8], data[full-BASE+28*8:full-BASE+55*8])
                self.assertEqual(info['matching_section_flags'], '0x10000100')
                self.assertTrue(info['valid_processing_not_established'])


if __name__ == '__main__':
    unittest.main()
