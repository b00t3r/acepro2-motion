import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_rawpiv_work_area import probe


class RawPivWorkAreaTests(unittest.TestCase):
    def test_caller_range_is_retained(self):
        for size in (31457280, 82944000):
            result = probe(0x80000000, size)
            self.assertEqual(result['start'], 0x80000000)
            self.assertEqual(result['cursor'], result['start'])
            self.assertEqual(result['end'], result['start'] + size)
            self.assertEqual(result['stored_size'], size)

    def test_null_or_zero_size_does_not_initialize(self):
        for base, size in ((0, 100), (0x80000000, 0)):
            result = probe(base, size)
            self.assertEqual(result['stored_size'], 0)
