"""Exercise the actual gallery-return branch, bitrate updater and callback."""
import functools
import struct
import sys
import unittest
from pathlib import Path

import lz4.frame
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X26)

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_gallery_bitrate_candidate import SOURCE, SOURCE_SHA, DEST, BASE, PATCH, REPLACEMENT, BITRATE
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_harness import Harness, CONTEXT, run_livephoto_config, run_still_geometry_fragment
from audit_capture_pipeline import pureshot_format
from test_motion_candidate import Machine


@functools.lru_cache(maxsize=1)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload'])
                 for p in (SOURCE,DEST))


def gallery(image, resolution=226, narrow=0, cached=37*1024*1024, target=BITRATE):
    h=Harness(image)
    h.uc.mem_map(0x12100000,0x1000)
    cfg=CONTEXT+0x18cfc
    packed=bytearray(0x70)
    struct.pack_into('<H',packed,6,resolution)
    struct.pack_into('<I',packed,0x20,target)
    struct.pack_into('<H',packed,0x34,narrow)
    h.uc.mem_write(cfg,bytes(packed))
    h.uc.mem_write(0x12100b44,struct.pack('<I',cached))
    for reg,val in ((UC_ARM64_REG_X19,CONTEXT+0x18c00),
                    (UC_ARM64_REG_X20,CONTEXT),(UC_ARM64_REG_X26,cfg)):
        h.uc.reg_write(reg,val)
    h.mocks={0x2639a0:lambda uc:0,0x71b880:lambda uc:0,0x8b7520:lambda uc:0}
    def config(uc):
        if uc.reg_read(UC_ARM64_REG_X0)!=0x19:
            raise ValueError('Unexpected native bitrate configuration lookup')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1),bytes(8))
        return 0
    h.mocks[0x2e4380]=config
    h.stops.update({0x28cbc4:'live_setup_complete',0x28cdcc:'other_resource'})
    h.run(0x28caf0)
    return h,bytes(h.uc.mem_read(cfg,0x70))


class GalleryBitrateCandidateTests(unittest.TestCase):
    def test_exact_allowlist_and_other_partitions(self):
        self.assertEqual(sha(SOURCE.read_bytes()),SOURCE_SHA)
        wanted=bytearray(images()[0])
        wanted[PATCH-BASE:PATCH-BASE+4]=REPLACEMENT
        for at in USB_OFFSETS:wanted[at:at+18]=b'Insta360 Ace Pro Q'
        self.assertEqual(images()[1],wanted)
        a,b=(unpack_package(p.read_bytes()) for p in (SOURCE,DEST))
        self.assertEqual(a['parts'][1:],b['parts'][1:])
        self.assertEqual(SOURCE.stat().st_size,DEST.stat().st_size)

    def test_actual_resource_guard_excludes_ordinary_modes(self):
        for res in list(range(236))+[65535]:
            h,packed=gallery(images()[1],resolution=res)
            self.assertEqual(h.outcome,'live_setup_complete' if res in (226,227,228) else 'other_resource')
            if res not in (226,227,228):
                self.assertNotIn(0x8b7520,h.calls)
                self.assertEqual(struct.unpack_from('<I',packed,0x20)[0],BITRATE)

    def test_reproduces_cached_override_and_preserves_native_updates(self):
        for res in (226,227,228):
            for narrow in (0,1):
                for cached in (0,2*1024*1024,37*1024*1024,100*1024*1024):
                    old,a=gallery(images()[0],res,narrow,cached)
                    new,b=gallery(images()[1],res,narrow,cached)
                    self.assertEqual(struct.unpack_from('<I',a,0x20)[0],cached)
                    self.assertEqual(struct.unpack_from('<I',b,0x20)[0],BITRATE)
                    a=bytearray(a);a[0x20:0x24]=b[0x20:0x24]
                    self.assertEqual(a,b)
                    # A changed target emits extra native bitrate-update logs.
                    logging=(0x2639a0,0x71b880)
                    self.assertEqual([c for c in new.calls if c not in logging],
                                     [c for c in old.calls if c not in logging])
                    self.assertIn(0x8b7520,new.calls)
                    self.assertEqual(bytes(new.uc.mem_read(0x12100b40,4)),struct.pack('<I',BITRATE))
                    if not narrow:
                        self.assertEqual(bytes(new.uc.mem_read(CONTEXT+0xd5ec,4)),struct.pack('<I',BITRATE))

    def test_native_registered_callback_applies_selected_target(self):
        for index in (0,1):
            h=Harness(images()[1]);h.uc.mem_map(0x12100000,0x1000)
            h.uc.mem_write(0x12100b40,struct.pack('<IIH',BITRATE,37*1024*1024,index))
            observed=[]
            def encoder(uc):
                p=uc.reg_read(UC_ARM64_REG_X2)
                observed.append(struct.unpack('<I',bytes(uc.mem_read(p+4,4)))[0])
                return 0
            h.mocks={0x15c3420:lambda uc:CONTEXT,0x2639a0:lambda uc:0,
                     0x71b880:lambda uc:0,0x1040f80:encoder,
                     0x27fc40:lambda uc:0,0x27fc00:lambda uc:0}
            h.run(0x288500)
            self.assertEqual(observed,[BITRATE])
            self.assertEqual(bytes(h.uc.mem_read(CONTEXT+0xd5ec+0x500*index,4)),struct.pack('<I',BITRATE))

    def test_photo_video_configuration_and_colour_are_unchanged(self):
        for resolution in (226,227,228):
            for narrow in (0,1):
                self.assertEqual(run_livephoto_config(resolution,narrow=narrow,image_data=images()[0],include_encoding=True),
                                 run_livephoto_config(resolution,narrow=narrow,image_data=images()[1],include_encoding=True))
        for live in (False,True):
            self.assertEqual(run_still_geometry_fragment(live,image_data=images()[0]),
                             run_still_geometry_fragment(live,image_data=images()[1]))
            for narrow in (0,1):
                self.assertEqual(pureshot_format(narrow,1,image_data=images()[0],livephoto=live),
                                 pureshot_format(narrow,1,image_data=images()[1],livephoto=live))

    def test_actual_motion_photo_hook_preserves_inputs(self):
        m=Machine(image_data=images()[1]);m.run()
        self.assertEqual(m.files[m.path],m.jpeg)
        self.assertEqual(m.files[m.path[:-4]+'.lrv'],m.lrv)
        self.assertIn(m.path[:-4]+'.MP.jpg',m.files)
