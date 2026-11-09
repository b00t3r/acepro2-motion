"""Test the conservative status mapping independently of camera I/O."""
import ctypes
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ClassificationTests(unittest.TestCase):
    def test_classification(self):
        out = ROOT / 'builds/offline-gallery-motion/stat-classify-test.dylib'
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['clang', '-dynamiclib', '-O2', str(ROOT / 'tools/motion_stat_classify.c'), '-o', str(out)], check=True)
        classify = ctypes.CDLL(str(out)).motion_stat_candidate_classify
        classify.argtypes = [ctypes.c_int, ctypes.c_uint]
        classify.restype = ctypes.c_int
        for result, detail, expected in [(0, 0, 1), (2, 3, 0), (2, 9, -1), (1, 3, -1), (3, 0, -1), (2, 49, -1), (0, 3, -1)]:
            with self.subTest(result=result, detail=detail):
                self.assertEqual(classify(result, detail), expected)
