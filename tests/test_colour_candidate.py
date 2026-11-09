"""Run Trial N's packaged instructions against the paired hardware inputs."""
import functools
import struct
import sys
import unittest
from pathlib import Path

import lz4.frame
from unicorn.arm64_const import *

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from build_colour_candidate import SOURCE, SOURCE_SHA, DEST, BASE, HOOK, STUB, patch_bytes
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_geometry_patch import branch
from livephoto_harness import Harness, run_still_geometry_fragment, run_livephoto_config
from audit_capture_pipeline import pureshot_format


@functools.lru_cache(maxsize=1)
def candidate():
    return lz4.frame.decompress(unpack_package(DEST.read_bytes())['parts'][0]['payload'])


class ColourCandidateTests(unittest.TestCase):
    def test_exact_allowlist_and_preserved_motion_photo_payload(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        source = unpack_package(SOURCE.read_bytes())
        result = unpack_package(DEST.read_bytes())
        expected = bytearray(lz4.frame.decompress(source['parts'][0]['payload']))
        expected[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
        expected[STUB-BASE:STUB-BASE+32] = patch_bytes()
        for offset in USB_OFFSETS:
            expected[offset:offset+18] = b'Insta360 Ace Pro N'
        self.assertEqual(candidate(), expected)
        self.assertEqual(result['parts'][1:], source['parts'][1:])
        self.assertEqual(DEST.stat().st_size, SOURCE.stat().st_size)

    def test_logged_binned_live_frames_use_same_format_at_both_zoom_levels(self):
        for live in (1, 2, 3, 4):
            for narrow in (0, 1):
                for sensor in (0, 1, 2, 7):
                    result = pureshot_format(narrow, sensor, image_data=candidate(), livephoto=live)
                    self.assertEqual(result['qbc'], 0)

    def test_regular_photo_format_decisions_are_unchanged(self):
        for narrow in (0, 1):
            for width in (4096, 8192):
                for sensor in (0, 1, 2, 7):
                    self.assertEqual(pureshot_format(narrow, sensor, width),
                                     pureshot_format(narrow, sensor, width, image_data=candidate()))

    def test_full_width_still_remains_qbc_even_with_live_flag(self):
        self.assertEqual(pureshot_format(1, raw_width=8192, image_data=candidate(),
                                        livephoto=True)['qbc'], 1)

    def test_stub_preserves_registers_stack_flags_and_global_zoom(self):
        for live in (0, 1):
            h = Harness(candidate())
            sp = h.uc.reg_read(UC_ARM64_REG_SP)
            h.uc.mem_write(sp+0x10c, b'\x01')
            h.uc.mem_write(0x1262e904, struct.pack('<I', live))
            h.uc.reg_write(UC_ARM64_REG_X9, 0x123456789abcdef0)
            h.uc.reg_write(UC_ARM64_REG_X30, 0x71000000)
            h.uc.reg_write(UC_ARM64_REG_NZCV, 0xa0000000)
            h.stops[HOOK+4] = 'hook_continuation'
            h.run(HOOK)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X0), 0 if live else 1)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X9), 0x123456789abcdef0)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X30), 0x71000000)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP), sp)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_NZCV), 0xa0000000)
            self.assertEqual(bytes(h.uc.mem_read(sp+0x10c, 1)), b'\x01')

    def test_zoom_geometry_and_video_configuration_are_preserved(self):
        original = lz4.frame.decompress(unpack_package(SOURCE.read_bytes())['parts'][0]['payload'])
        for live in (False, True):
            self.assertEqual(run_still_geometry_fragment(live, image_data=original),
                             run_still_geometry_fragment(live, image_data=candidate()))
        for narrow in (0, 1):
            self.assertEqual(run_livephoto_config(226, narrow=narrow, image_data=original),
                             run_livephoto_config(226, narrow=narrow, image_data=candidate()))
