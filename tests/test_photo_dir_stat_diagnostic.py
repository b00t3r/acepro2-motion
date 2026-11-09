"""Check the photo-directory variant with mocked ARM filesystem calls."""
import json
import unittest
from test_stat_diagnostic import StatDiagnosticTests
from build_photo_dir_stat_diagnostic import build,OUT,ROOT

class PhotoDirStatTests(StatDiagnosticTests):
    @classmethod
    def setUpClass(cls):
        build()
        cls.report=json.loads((ROOT/'builds/offline-stat-diagnostic/report.json').read_text())
        cls.image=(OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def test_marker_gates_three_read_only_queries(self):
        r=self.run_case()
        self.assertEqual(r['armed'],1)
        self.assertEqual(r['paths'],['C:\\RAW8K.ENABLE','C:\\DCIM\\Camera01\\CXMISS001.TST',
                                     'Z:\\CODEX_STAT_MISSING_4271.TST'])
        self.assertEqual(r['logs'],[(0,0,0),(1,2,49),(2,2,9)])

    def test_packaged_candidate_contains_only_audited_changes(self):
        import lz4.frame
        from build_photo_dir_stat_diagnostic import SOURCE,DEST,OLD,NEW
        from build_usb_name_candidate import unpack_package,USB_OFFSETS
        before=lz4.frame.decompress(unpack_package(SOURCE.read_bytes())['parts'][0]['payload'])
        after=lz4.frame.decompress(unpack_package(DEST.read_bytes())['parts'][0]['payload'])
        pos=before.index(OLD);allowed=set(range(pos,pos+len(OLD)))
        for off in USB_OFFSETS:allowed.update(range(off,off+18))
        self.assertTrue(all(i in allowed for i,(x,y) in enumerate(zip(before,after)) if x!=y))
        self.assertEqual(after[pos:pos+len(NEW)],NEW)
