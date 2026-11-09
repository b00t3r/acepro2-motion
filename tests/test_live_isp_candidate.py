"""Native execution and exact package scope for the Trial U ISP experiment."""
import functools
import struct
import sys
import unittest
from pathlib import Path
import lz4.frame
from unicorn.arm64_const import *
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_zoom_isp_selection import replay, PARAMS
from build_live_isp_candidate import SOURCE, SOURCE_SHA, DEST, BASE, HOOK, STUB, patch_bytes
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_geometry_patch import branch
from livephoto_harness import Harness, run_still_geometry_fragment, run_livephoto_config
from audit_capture_pipeline import pureshot_format


@functools.lru_cache(None)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload']) for p in (SOURCE, DEST))


class LiveIspCandidateTests(unittest.TestCase):
    def test_zoom_geometry_stream_and_pureshot_format_remain_unchanged(self):
        old, new = images()
        for live in (False, True):
            self.assertEqual(run_still_geometry_fragment(live, image_data=old),
                             run_still_geometry_fragment(live, image_data=new))
        for narrow in (0, 1):
            for res in (226, 227, 228):
                self.assertEqual(run_livephoto_config(res, narrow=narrow, image_data=old),
                                 run_livephoto_config(res, narrow=narrow, image_data=new))
            self.assertEqual(pureshot_format(narrow, image_data=old, livephoto=True),
                             pureshot_format(narrow, image_data=new, livephoto=True))

    def test_exact_change_scope(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        old, new = images()
        expected = bytearray(old)
        expected[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
        expected[STUB-BASE:STUB-BASE+len(patch_bytes())] = patch_bytes()
        for at in USB_OFFSETS:
            expected[at:at+18] = b'Insta360 Ace Pro U'
        self.assertEqual(new, expected)
        self.assertEqual(unpack_package(SOURCE.read_bytes())['parts'][1:], unpack_package(DEST.read_bytes())['parts'][1:])

    def test_full_native_selection_uses_one_x_live_tuning_and_preserves_other_cases(self):
        old, new = images()
        for face in (0, 1):
            for raw in (0, 1):
                for rec in (0, 1):
                    for narrow in (0, 1):
                        for live in (0, 1):
                            kwargs = dict(recording=rec, face=face, still_type=raw, live_flag=live)
                            actual = replay(narrow=narrow, image_data=new, **kwargs)
                            expected = replay(narrow=0 if live else narrow, image_data=old, **kwargs)
                            self.assertEqual((actual['row'], actual['root']), (expected['row'], expected['root']), (kwargs, narrow))
                            if live:
                                self.assertIn('livephoto', actual['table'])

    def test_stub_guards_preserve_state_and_only_mask_local_narrow(self):
        new = images()[1]
        for live in (0, 1):
            for sensor in (7, 8):
                for mode in (0, 1):
                    for submode in (12, 17):
                        for narrow in (0, 1, 2):
                            h = Harness(new)
                            h.uc.mem_write(PARAMS+0x34, struct.pack('<II', narrow, 123))
                            h.uc.mem_write(0x1262e904, struct.pack('<I', live))
                            for reg, value in [(UC_ARM64_REG_X22, PARAMS), (UC_ARM64_REG_X3, sensor),
                                               (UC_ARM64_REG_X4, mode), (UC_ARM64_REG_X5, submode),
                                               (UC_ARM64_REG_X9, 0x123456789abcdef0),
                                               (UC_ARM64_REG_X10, 0xfedcba9876543210),
                                               (UC_ARM64_REG_NZCV, 0xa0000000)]:
                                h.uc.reg_write(reg, value)
                            regs = [UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                                    UC_ARM64_REG_X9, UC_ARM64_REG_X10, UC_ARM64_REG_X22,
                                    UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_NZCV]
                            before = [h.uc.reg_read(r) for r in regs]
                            h.stops[HOOK+4] = 'returned_to_selector'
                            h.run(HOOK)
                            mask = live and sensor==8 and mode==1 and submode==17 and narrow==1
                            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X16), 0 if mask else narrow)
                            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X17), 123)
                            self.assertEqual([h.uc.reg_read(r) for r in regs], before)
                            self.assertEqual(bytes(h.uc.mem_read(PARAMS+0x34, 8)), struct.pack('<II', narrow, 123))


if __name__ == '__main__':
    unittest.main()
