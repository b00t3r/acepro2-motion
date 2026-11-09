import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_worker_placement import native_regions,descriptor_bits
from build_background_prototype import WORKER_BASE,WORKER_END


class WorkerPlacementTests(unittest.TestCase):
    def test_gap_and_root_slot_share_native_mapping_with_existing_payload(self):
        regions=native_regions();r=regions[1]
        self.assertEqual(r['virtual'],0x50000)
        self.assertEqual(r['physical'],0x50000)
        self.assertEqual(r['attributes'],0x770c49)
        self.assertGreaterEqual(WORKER_BASE,0x2552008)
        self.assertLessEqual(WORKER_END+8,regions[2]['virtual'])
        self.assertEqual(regions[2]['virtual'],0x2553000)
        self.assertLess(WORKER_END+8,r['virtual']+r['size'])

    def test_native_descriptor_encoding_permits_state_and_code(self):
        r=descriptor_bits(native_regions()[1]['attributes'])
        self.assertEqual(r['access_permission_bits'],0)
        self.assertFalse(r['privileged_execute_never'])
        self.assertFalse(r['execute_never'])
