"""Reproduce the format-selection change observed in the paired hardware logs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_capture_pipeline import pureshot_format


class CapturePipelineAudit(unittest.TestCase):
    def test_zoom_alone_changes_raw_processing_format_for_logged_frame_mode(self):
        self.assertEqual(pureshot_format(0)['qbc'], 0)
        self.assertEqual(pureshot_format(1)['qbc'], 1)

    def test_sensor_configuration_can_also_select_qbc_without_zoom(self):
        self.assertEqual(pureshot_format(0, raw_width=8192)['qbc'], 1)
