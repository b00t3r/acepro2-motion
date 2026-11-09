"""Verify real packaged large-buffer copies and failure cleanup, without hardware claims."""
import functools
import struct
import unittest
import lz4.frame
from test_motion_candidate import Machine, ROOT
from test_gallery_bitrate_candidate import gallery
from build_fast_copy_candidate import SOURCE, SOURCE_SHA, DEST, BASE, CAVE, PAYLOAD_END, OUT, COPY_BYTES
from build_motion_candidate import sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from livephoto_harness import run_livephoto_config, run_still_geometry_fragment
from audit_capture_pipeline import pureshot_format


@functools.lru_cache(maxsize=1)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload'])
                 for p in (SOURCE,DEST))


class CountedMachine(Machine):
    def __init__(self,*args,**kwargs):
        self.read_sizes=[];self.write_sizes=[];self.alloc_sizes=[]
        super().__init__(*args,**kwargs)

    def alloc(self):
        n=self.arg(1);self.alloc_sizes.append(n)
        if self.fail=='alloc':return 1
        assert n in (5120,COPY_BYTES+1024)
        self.uc.mem_write(self.arg(0),struct.pack('<Q',0x50002000))
        self.allocated=True
        return 0

    def read(self):
        self.read_sizes.append(self.arg(1)*self.arg(2))
        return super().read()

    def write(self):
        self.write_sizes.append(self.arg(1)*self.arg(2))
        return super().write()


class FastCopyCandidateTests(unittest.TestCase):
    def test_exact_payload_scope_and_preserved_partitions(self):
        self.assertEqual(sha(SOURCE.read_bytes()),SOURCE_SHA)
        wanted=bytearray(images()[0]);payload=(OUT/'payload.bin').read_bytes()
        self.assertLessEqual(CAVE+len(payload),PAYLOAD_END)
        wanted[CAVE-BASE:PAYLOAD_END-BASE]=payload+bytes(PAYLOAD_END-CAVE-len(payload))
        for at in USB_OFFSETS:wanted[at:at+18]=b'Insta360 Ace Pro R'
        self.assertEqual(images()[1],wanted)
        self.assertEqual(SOURCE.stat().st_size,DEST.stat().st_size)
        self.assertEqual(unpack_package(SOURCE.read_bytes())['parts'][1:],
                         unpack_package(DEST.read_bytes())['parts'][1:])

    def test_real_camera_pair_output_is_byte_identical_with_native_formatter(self):
        folder=ROOT/'analysis/gallery-bitrate-trial-q-hardware'
        for stem in ('LIV_20261029_152411_936','LIV_20261029_152417_937'):
            opts=dict(jpeg=(folder/(stem+'.jpg')).read_bytes(),
                      lrv=(folder/(stem+'.lrv')).read_bytes(),native_format=True)
            old=CountedMachine(image_data=images()[0],**opts)
            new=CountedMachine(image_data=images()[1],**opts)
            self.assertEqual(old.run(),new.run())
            self.assertEqual(new.alloc_sizes,[COPY_BYTES+1024])

    def test_large_copies_reduce_filesystem_calls(self):
        opts=dict(lrv=b'\0\0\0\x18ftypavc1'+b'B'*(1024*1024+31))
        old=CountedMachine(image_data=images()[0],**opts)
        new=CountedMachine(image_data=images()[1],**opts)
        self.assertEqual(old.run(),new.run())
        self.assertIn(COPY_BYTES,new.write_sizes)
        self.assertLess(len(new.write_sizes)*8,len(old.write_sizes))
        self.assertLess(len(new.read_sizes),len(old.read_sizes))
        self.assertLessEqual(max(new.read_sizes),COPY_BYTES)
        self.assertLessEqual(max(new.write_sizes),COPY_BYTES)

    def test_errors_leave_originals_and_never_publish_partial_file(self):
        for fail in ('missing_lrv','open_dest','read','write','seek','alloc','format','close_dest','rename'):
            with self.subTest(fail=fail):
                m=CountedMachine(image_data=images()[1],fail=fail)
                self.assertIsNone(m.run())
                self.assertNotIn(m.path[:-4]+'.MP.jpg',m.files)

    def test_existing_outputs_and_nonlive_callbacks_are_skipped(self):
        for opts in ({'live':0},{'status':1},{'name':'IMG_20261029_152411_936.jpg'},
                     {'existing':{'C:\\DCIM\\Camera01\\LIV_20261027_200749_030.MP.jpg':b'existing'}}):
            m=CountedMachine(image_data=images()[1],**opts);m.run()
            self.assertEqual(m.alloc_sizes,[])

    def test_gallery_bitrate_photo_colour_and_geometry_are_unchanged(self):
        for res in (226,227,228):
            for narrow in (0,1):
                a,b=(gallery(im,res,narrow)[1] for im in images())
                self.assertEqual(a,b)
                self.assertEqual(run_livephoto_config(res,narrow=narrow,image_data=images()[0],include_encoding=True),
                                 run_livephoto_config(res,narrow=narrow,image_data=images()[1],include_encoding=True))
        for live in (False,True):
            self.assertEqual(run_still_geometry_fragment(live,image_data=images()[0]),
                             run_still_geometry_fragment(live,image_data=images()[1]))
            for narrow in (0,1):
                self.assertEqual(pureshot_format(narrow,1,image_data=images()[0],livephoto=live),
                                 pureshot_format(narrow,1,image_data=images()[1],livephoto=live))
