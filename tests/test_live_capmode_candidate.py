"""Execute the actual native selector, its persistent store, and repeated calls."""
import functools
import struct
import sys
import unittest
from pathlib import Path
import lz4.frame
from unicorn.arm64_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_live_capmode_candidate import SOURCE,SOURCE_SHA,DEST,BASE,HOOK,STUB,patch_bytes
from build_usb_name_candidate import unpack_package,USB_OFFSETS
from build_motion_candidate import sha
from livephoto_geometry_patch import branch
from livephoto_harness import Harness,CONTEXT,run_still_geometry_fragment,run_livephoto_config
from audit_capture_pipeline import pureshot_format


@functools.lru_cache(None)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload']) for p in (SOURCE,DEST))


def select(data,mode,narrow,live,factory=2):
    h=Harness(data)
    sp=h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp+0xaf,bytes([narrow]))
    h.uc.mem_write(sp+0xb3,struct.pack('<I',factory))
    # Native 0x282414 advances x28 by 0x18000 before accessing +0x800.
    h.uc.mem_write(CONTEXT+0x18800,struct.pack('<I',mode))
    h.uc.mem_write(0x1262e904,struct.pack('<I',live))
    h.uc.reg_write(UC_ARM64_REG_X28,CONTEXT)
    h.stops[0x28245c]='selected'
    h.run(0x282410)
    return struct.unpack('<I',h.uc.mem_read(CONTEXT+0x18800,4))[0]


class LiveCapmodeCandidateTests(unittest.TestCase):
    def test_exact_scope_and_s_reverted(self):
        self.assertEqual(sha(SOURCE.read_bytes()),SOURCE_SHA)
        old,new=images()
        expected=bytearray(old)
        expected[HOOK-BASE:HOOK-BASE+4]=branch(HOOK,STUB)
        expected[STUB-BASE:STUB-BASE+32]=patch_bytes()
        for at in USB_OFFSETS:
            expected[at:at+18]=b'Insta360 Ace Pro T'
        self.assertEqual(new,expected)
        self.assertEqual(new[0x282454-BASE:0x282458-BASE],bytes.fromhex('0000841a'))
        self.assertEqual(unpack_package(SOURCE.read_bytes())['parts'][1:],unpack_package(DEST.read_bytes())['parts'][1:])

    def test_native_persistent_assignment_changes_only_live_narrow_cases(self):
        old,new=images()
        for mode in (0,3,9,27,33,35,36):
            for narrow in (0,1):
                for live in (0,1):
                    for factory in (1,2):
                        baseline=select(old,mode,narrow,live,factory)
                        actual=select(new,mode,narrow,live,factory)
                        expected=36 if live and narrow and mode in (3,9,36) else baseline
                        self.assertEqual(actual,expected,(mode,narrow,live,factory))

    def test_repeated_two_x_live_calls_do_not_persist_27(self):
        old,new=images()
        mode=36
        for _ in range(4):
            mode=select(new,mode,1,1)
            self.assertEqual(mode,36)
        self.assertEqual(select(old,36,1,1),27)
        self.assertEqual(select(new,36,1,0),27)

    def test_stub_preserves_registers_flags_stack_and_link(self):
        for live in (0,1):
            h=Harness(images()[1])
            sp=h.uc.reg_read(UC_ARM64_REG_SP)
            h.uc.reg_write(UC_ARM64_REG_X9,0x123456789abcdef0)
            h.uc.reg_write(UC_ARM64_REG_NZCV,0xa0000000)
            lr=h.uc.reg_read(UC_ARM64_REG_X30)
            h.uc.mem_write(0x1262e904,struct.pack('<I',live))
            h.stops[HOOK+4]='return_to_native_store'
            h.run(HOOK)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X0),36 if live else 27)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X9),0x123456789abcdef0)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_NZCV),0xa0000000)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP),sp)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X30),lr)

    def test_existing_geometry_stream_and_raw_format_decisions_preserved(self):
        old,new=images()
        for live in (False,True):
            self.assertEqual(run_still_geometry_fragment(live,image_data=old),run_still_geometry_fragment(live,image_data=new))
        for narrow in (0,1):
            for res in (226,227,228):
                self.assertEqual(run_livephoto_config(res,narrow=narrow,image_data=old),run_livephoto_config(res,narrow=narrow,image_data=new))
            self.assertEqual(pureshot_format(narrow,image_data=old,livephoto=True),pureshot_format(narrow,image_data=new,livephoto=True))
