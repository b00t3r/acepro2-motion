"""Exercise the delete probe in ARM emulation with a fake filesystem."""
import unittest
from test_rename_diagnostic import DiagnosticTests
from build_rename_diagnostic import build,ROOT

class DeleteDiagnosticTests(DiagnosticTests):
    @classmethod
    def setUpClass(cls):
        cls.report=build('delete')
        cls.image=(ROOT/'builds/offline-delete-diagnostic/main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def test_collision_results_and_one_attempt(self):
        calls,logs=self.run_case(repeat=True)
        self.assertEqual([c for c in calls if c[0]=='delete'],[('delete','C:\\CXR7139\\S.TST')])
        self.assertEqual(logs[0][:3],[0,0xffffffff,1])

    def test_gates_and_failures_do_not_rename(self):
        for opts in ({'armed':False},{'valid':False},{'resource':226},{'read_failure':True}):
            with self.subTest(**opts):
                calls,_=self.run_case(**opts)
                self.assertFalse(any(c[0]=='delete' for c in calls))
                self.assertTrue(all(c[2]=='rb' for c in calls if c[0]=='open'))
