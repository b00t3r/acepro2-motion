import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_video_buffer_cap import allocation_cap


class VideoBufferCapProbe(unittest.TestCase):
    def test_native_cap_matches_hardware_allocation(self):
        self.assertEqual(allocation_cap(0x2d6dac80), 536838144)

    def test_emulator_only_cap_releases_exactly_256_mib(self):
        free = 0x2d6dac80
        self.assertEqual(allocation_cap(free) - allocation_cap(free, True), 256 * 1024**2)
        self.assertEqual(allocation_cap(free, True), 0x0fff8000)

    def test_free_memory_bound_is_preserved(self):
        for free in (0, 0x2000000, 0x0fff7fff, 0x0fff8000):
            self.assertEqual(allocation_cap(free, True), free)

    def test_uint32_size_is_enforced(self):
        for free in (-1, 2**32):
            with self.assertRaises(ValueError):
                allocation_cap(free)


if __name__ == '__main__':
    unittest.main()
