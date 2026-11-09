import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import lz4.frame
from unicorn.arm64_const import UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4
from build_fullsensor_marker_diagnostic import DEST, SOURCE, SOURCE_SHA
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package
from livephoto_harness import CONTEXT, ROOT, run_livephoto_config


class MarkerOnlyDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = unpack_package(SOURCE.read_bytes())
        cls.dst = unpack_package(DEST.read_bytes())
        cls.before = lz4.frame.decompress(cls.src['parts'][0]['payload'])
        cls.after = lz4.frame.decompress(cls.dst['parts'][0]['payload'])

    def test_package_and_preserved_motion_payload(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        self.assertEqual(len(DEST.read_bytes()), len(SOURCE.read_bytes()))
        self.assertEqual(self.src['parts'][1:], self.dst['parts'][1:])
        for start, end in ((0x2552020, 0x2552c40), (0x50240, 0x50f80)):
            self.assertEqual(self.before[start-0x50000:end-0x50000], self.after[start-0x50000:end-0x50000])

    def test_native_config_unchanged_and_status_logged(self):
        for resource, narrow, present, close_ok in ((227, 1, False, True),
                (227, 1, True, True), (227, 1, True, False), (227, 0, True, True),
                (226, 1, True, True)):
            calls = []
            def open_mock(uc):
                calls.append('open')
                if present: uc.mem_write(uc.reg_read(UC_ARM64_REG_X2), struct.pack('<Q', CONTEXT+0x500))
                return 0 if present else 1
            def close_mock(uc):
                calls.append('close')
                return 0 if close_ok else 1
            def log_mock(uc):
                fmt = bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X3), 32)).split(b'\0')[0]
                calls.append(('log', fmt, uc.reg_read(UC_ARM64_REG_X4)))
                return 0
            old = run_livephoto_config(resource, narrow, image_data=self.before, include_encoding=True)
            new = run_livephoto_config(resource, narrow, image_data=self.after, include_encoding=True,
                extra_mocks={0x26a860: open_mock, 0x26a8a0: close_mock, 0x71b880: log_mock})
            self.assertEqual(old['packed_config_hex'], new['packed_config_hex'])
            # Filter native logging, which the harness also mocks at this address.
            diagnostic = [x for x in calls if isinstance(x, tuple) and x[1] == b'marker status %u']
            if resource == 227:
                self.assertEqual([x[2] for x in diagnostic], [1 if present and close_ok else 2 if present else 0])
            else:
                self.assertEqual(diagnostic, [])
                self.assertNotIn('open', calls)


if __name__ == '__main__': unittest.main()
