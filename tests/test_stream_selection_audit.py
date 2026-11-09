"""Catch the separate pre-recording selection missed by a recording-mask edit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit_stream_selection import record_mask, prerecord_stream_ids


class StreamSelectionAudit(unittest.TestCase):
    def test_lrv_only_recording_mask_does_not_select_lrv_only_prerecording(self):
        self.assertEqual(record_mask(2), 2)
        self.assertEqual(prerecord_stream_ids(), [0, 1])

    def test_native_single_stream_configuration_forces_main_stream(self):
        self.assertEqual(record_mask(2, count=1), 1)
        self.assertEqual(prerecord_stream_ids(count=1), [0])
