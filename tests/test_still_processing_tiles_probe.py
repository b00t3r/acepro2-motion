import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_still_processing_tiles import probe


class StillProcessingTilesProbeTests(unittest.TestCase):
    def test_full_width_requires_different_native_dsp_configuration(self):
        live = probe(4096)
        full = probe(8192)
        self.assertEqual(live['configuration_words'], [1, 4, 1])
        self.assertEqual(full['configuration_words'], [1, 6, 1])
        self.assertTrue(full['dsp_call_mocked'])

    def test_a_20mp_output_width_is_not_a_substitute_for_the_full_input_width(self):
        self.assertEqual(probe(5120)['configuration_words'], [1, 4, 1])
        self.assertEqual(probe(8192)['configuration_words'], [1, 6, 1])


if __name__ == '__main__':
    unittest.main()
