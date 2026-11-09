"""Verify all native Live Photo bitrate paths and unchanged image/save behaviour."""
import functools
import struct
import sys
import unittest
from pathlib import Path

import lz4.frame
from unicorn.arm64_const import UC_ARM64_REG_X0

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_small_main_candidate import SOURCE, SOURCE_SHA, DEST, BASE, PATCHES, REPLACEMENT, BITRATE
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_harness import Harness, CONTEXT, run_livephoto_config, run_still_geometry_fragment
from audit_capture_pipeline import pureshot_format
from test_motion_candidate import Machine


@functools.lru_cache(maxsize=1)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload'])
                 for p in (SOURCE,DEST))


class SmallMainCandidateTests(unittest.TestCase):
    def test_exact_allowlist_and_preserved_partitions(self):
        self.assertEqual(sha(SOURCE.read_bytes()),SOURCE_SHA)
        expected=bytearray(images()[0])
        for address in PATCHES:
            expected[address-BASE:address-BASE+4]=REPLACEMENT
        for at in USB_OFFSETS:
            expected[at:at+18]=b'Insta360 Ace Pro P'
        self.assertEqual(images()[1],expected)
        a,b=(unpack_package(p.read_bytes()) for p in (SOURCE,DEST))
        self.assertEqual(a['parts'][1:],b['parts'][1:])
        self.assertEqual(SOURCE.stat().st_size,DEST.stat().st_size)

    def test_native_configuration_all_bitrate_paths_change_only_bitrate(self):
        for resolution in (226,227,228):
            for narrow in (0,1):
                for standard in (0,1):
                    for custom in (0,1):
                        for lowlight in (0,1):
                            config={0x24:bytes([standard]),0x1b:struct.pack('<II',custom,0),
                                    0x3d:bytes([0,lowlight,0,0])}
                            with self.subTest(resolution=resolution,narrow=narrow,
                                              standard=standard,custom=custom,lowlight=lowlight):
                                old,new=(run_livephoto_config(resolution,narrow=narrow,image_data=im,
                                         config_overrides=config,include_encoding=True) for im in images())
                                self.assertEqual(new['target_bitrate'],BITRATE)
                                a,b=(bytearray.fromhex(r['packed_config_hex']) for r in (old,new))
                                a[0x20:0x24]=b[0x20:0x24]
                                self.assertEqual(a,b)
                                self.assertEqual(old['dimensions'],new['dimensions'])
                                self.assertEqual(old['fps_numerator'],new['fps_numerator'])
                                self.assertEqual(old['fps_denominator'],new['fps_denominator'])

    def test_native_live_configuration_wrapper_retains_enable_gate(self):
        for enabled in (0,1):
            h=Harness(images()[1])
            cfg=CONTEXT+0x1000
            before=bytes([0x5a])*0x70
            h.uc.mem_write(cfg,before)
            h.uc.mem_write(0x1262e900,bytes([enabled]))
            h.uc.reg_write(UC_ARM64_REG_X0,cfg)
            h.mocks={0x15c3420:lambda uc:CONTEXT,0x293ec0:lambda uc:1,
                     0x28d700:lambda uc:0,0x2639a0:lambda uc:0,0x71b880:lambda uc:0}
            h.stops[0x401480]='live_config_reached'
            h.run(0x402f00)
            self.assertEqual(h.outcome,'live_config_reached' if enabled else 'returned')
            self.assertEqual(bytes(h.uc.mem_read(cfg,len(before))),before)

    def test_pureshot_fix_and_still_zoom_geometry_are_preserved(self):
        for live in (False,True):
            for narrow in (0,1):
                self.assertEqual(pureshot_format(narrow,1,image_data=images()[0],livephoto=live),
                                 pureshot_format(narrow,1,image_data=images()[1],livephoto=live))
            self.assertEqual(run_still_geometry_fragment(live,image_data=images()[0]),
                             run_still_geometry_fragment(live,image_data=images()[1]))

    def test_packaged_motion_photo_hook_preserves_original_inputs(self):
        m=Machine(image_data=images()[1])
        m.run()
        self.assertEqual(m.files[m.path],m.jpeg)
        self.assertEqual(m.files[m.path[:-4]+'.lrv'],m.lrv)
        self.assertTrue(m.path[:-4]+'.MP.jpg' in m.files)
