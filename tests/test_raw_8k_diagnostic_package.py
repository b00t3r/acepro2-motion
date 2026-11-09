import sys
import unittest
from pathlib import Path
import lz4.frame

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_raw_8k_diagnostic_candidate import SOURCE,DEST,package
from build_raw_8k_diagnostic_offline import HOOK,CONFIG_HOOK,LOG_LEVEL,STUB,END
from build_usb_name_candidate import unpack_package,USB_OFFSETS
from livephoto_harness import BASE


class DiagnosticPackageTests(unittest.TestCase):
    def test_package_changes_only_expected_image_regions(self):
        report=package()
        a=unpack_package(SOURCE.read_bytes())
        b=unpack_package(DEST.read_bytes())
        before=lz4.frame.decompress(a['parts'][0]['payload'])
        after=lz4.frame.decompress(b['parts'][0]['payload'])
        self.assertEqual(a['parts'][1:],b['parts'][1:])
        allowed=set(range(HOOK-BASE,HOOK-BASE+4))|set(range(STUB-BASE,END-BASE))
        allowed.update(range(CONFIG_HOOK-BASE,CONFIG_HOOK-BASE+4))
        allowed.update(range(LOG_LEVEL-BASE,LOG_LEVEL-BASE+4))
        for at in USB_OFFSETS: allowed.update(range(at,at+18))
        changed={i for i,(old,new) in enumerate(zip(before,after)) if old!=new}
        self.assertTrue(changed)
        self.assertTrue(changed<=allowed)
        self.assertEqual(len(before),len(after))
        self.assertFalse(report['hardware_tested'])
        self.assertFalse(report['staged'])


if __name__=='__main__':
    unittest.main()
