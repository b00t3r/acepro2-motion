"""Validate native wrapper ABI with its scheduler calls explicitly mocked."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_background_save import task_create_contract
from livephoto_harness import CONTEXT


class BackgroundTaskContractTests(unittest.TestCase):
    def test_native_creation_affinity_and_resume_contract(self):
        r=task_create_contract()
        self.assertEqual(r['status'],0)
        self.assertEqual(r['task_state'],1)
        self.assertEqual(r['calls'],[
            {'callee':'native_task_create','args':[CONTEXT,CONTEXT+0x1000,80,
                0x50240,CONTEXT+0x1800,CONTEXT+0x2000,0x10000,0]},
            {'callee':'native_task_affinity','task':CONTEXT,'mask':1},
            {'callee':'native_task_resume','task':CONTEXT}])

    def test_invalid_priority_rejected_before_scheduler(self):
        r=task_create_contract(128)
        self.assertEqual(r['status'],22)
        self.assertEqual(r['calls'],[])
