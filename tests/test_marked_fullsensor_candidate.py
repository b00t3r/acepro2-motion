import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import lz4.frame
from unicorn.arm64_const import UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4
from build_marked_fullsensor_candidate import DEST, SOURCE, SOURCE_SHA, START, END
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_harness import BASE, CONTEXT, run_livephoto_config


class MarkedFullSensorCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = unpack_package(SOURCE.read_bytes())
        cls.dst = unpack_package(DEST.read_bytes())
        cls.before = lz4.frame.decompress(cls.src['parts'][0]['payload'])
        cls.after = lz4.frame.decompress(cls.dst['parts'][0]['payload'])

    def test_package_and_scoped_binary_changes(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        self.assertEqual(len(DEST.read_bytes()), len(SOURCE.read_bytes()))
        self.assertEqual(self.src['parts'][1:], self.dst['parts'][1:])
        expected = bytearray(self.before)
        expected[START-BASE:END-BASE] = self.after[START-BASE:END-BASE]
        for offset in USB_OFFSETS: expected[offset:offset+18] = b'Insta360 Ace Pro H'
        self.assertEqual(self.after, bytes(expected))

    def test_config_with_marker_and_error_paths(self):
        for resource, narrow, present, close_ok in ((227,0,True,True),(227,1,True,True),
                (227,0,False,True),(227,1,False,True),(227,1,True,False),
                (226,0,True,True),(226,1,True,True),(228,1,True,True)):
            logs = []
            def open_mock(uc):
                if present: uc.mem_write(uc.reg_read(UC_ARM64_REG_X2), struct.pack('<Q', CONTEXT+0x500))
                return 0 if present else 1
            def log_mock(uc):
                ptr=uc.reg_read(UC_ARM64_REG_X3)
                fmt=bytes(uc.mem_read(ptr,32)).split(b'\0')[0]
                if fmt==b'marker status %u': logs.append(uc.reg_read(UC_ARM64_REG_X4))
                return 0
            mocks = {0x26a860:open_mock, 0x26a8a0:lambda uc:0 if close_ok else 1, 0x71b880:log_mock}
            old = run_livephoto_config(resource, narrow, image_data=self.before, include_encoding=True, extra_mocks=mocks)
            logs.clear()
            new = run_livephoto_config(resource, narrow, image_data=self.after, include_encoding=True, extra_mocks=mocks)
            expected = bytearray.fromhex(old['packed_config_hex'])
            if resource == 227 and present and close_ok: struct.pack_into('<HH', expected, 8, 49, 49)
            self.assertEqual(new['packed_config_hex'], expected.hex())
            if resource == 227: self.assertEqual(logs, [1 if present and close_ok else 2 if present else 0])
            else: self.assertEqual(logs, [])


if __name__=='__main__': unittest.main()
