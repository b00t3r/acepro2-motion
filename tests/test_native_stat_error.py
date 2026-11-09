import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_native_stat_error import probe,probe_path_conversion_failure


class NativeStatErrorTests(unittest.TestCase):
    def test_native_stat_preserves_controlled_error_codes(self):
        for error in (1,2,5,49):
            with self.subTest(error=error):
                result=probe(error)
                self.assertEqual(result['native_return'],error)
                self.assertEqual(result['task_error'],error)

    def test_wrapper_collapses_return_but_task_error_remains(self):
        for error in (1,2,5,49):
            with self.subTest(error=error):
                result=probe(error,through_wrapper=True)
                self.assertEqual(result['native_return'],0x110004)
                self.assertEqual(result['task_error'],error)

    def test_path_conversion_failure_leaves_task_error_stale(self):
        result=probe_path_conversion_failure()
        self.assertEqual(result['wrapper_return'],0x110004)
        self.assertEqual(result['task_error'],0x12345678)
        self.assertEqual(result['global_conversion_error'],5)
