"""Software-only execution of the proposed payload; no firmware is built."""
import struct
import subprocess
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30
from test_fast_copy_candidate import CountedMachine, images
from build_background_prototype import link_regions
from livephoto_harness import BASE
from make_motion_photo import jpeg_end
from verify_device_motion_photo import check
from build_gallery_motion_offline import build as build_optimized
from test_background_worker_prototype import WorkerMachine
from test_background_save_candidate import images as background_images

ROOT = Path(__file__).resolve().parents[1]
ENTRY = 0x2558000  # Emulator memory only; not validated as a camera code cave.


class GalleryMotionPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = ROOT / 'builds/offline-gallery-motion'
        out.mkdir(parents=True, exist_ok=True)
        obj = out / 'payload-test.o'
        flags = ['-target','aarch64-none-elf','-Os','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics',
            '-DMOTION_CAPTURED_TIMESTAMP','-DMOTION_COPY_BYTES=65536','-DMOTION_GALLERY_TRAILER',
            '-DMOTION_DURABLE_SAVE']
        subprocess.run(['clang',*flags,'-c',str(ROOT/'tools/motion_photo_payload.c'),'-o',str(obj)],check=True)
        blobs, symbols, _ = link_regions([(ENTRY, ENTRY+0x2000, [obj])])
        assert symbols['motion_save_captured'] == ENTRY
        image = bytearray(images()[1])
        image[ENTRY-BASE:ENTRY-BASE+len(blobs[0])] = blobs[0]
        cls.image = bytes(image)

    def run_payload(self, **kwargs):
        m = CountedMachine(image_data=self.image, **kwargs)
        def sync():
            m.events.append(('sync',m.handles[m.arg(0)][0]))
            return int(m.fail=='sync')
        m.uc.hook_add(UC_HOOK_CODE,m.callback(sync),begin=0x26aa80,end=0x26aa80)
        m.uc.reg_write(UC_ARM64_REG_X0, 0x50000000)
        m.uc.reg_write(UC_ARM64_REG_X1, 1468)
        m.uc.reg_write(UC_ARM64_REG_X30, 0x71000000)
        m.uc.emu_start(ENTRY, 0x71000000, timeout=30000000, count=80000000)
        self.assertFalse(m.handles)
        self.assertFalse(m.allocated)
        for name, data in m.originals.items():
            self.assertEqual(bytes(m.files[name]), data)
        return m

    def test_camera_capture_and_trailer_layout(self):
        folder = ROOT/'analysis/gallery-bitrate-trial-q-hardware'
        for stem in ('LIV_20261029_152411_936','LIV_20261029_152417_937'):
            jpg = (folder/(stem+'.jpg')).read_bytes()
            video = (folder/(stem+'.lrv')).read_bytes()
            trailer = jpg[jpeg_end(jpg):]
            m = self.run_payload(jpeg=jpg, lrv=video)
            output = bytes(m.files[m.path[:-4]+'.MP.jpg'])
            embedded = video + struct.pack('>I4s',len(trailer)+8,b'free') + trailer
            self.assertTrue(check(jpg, embedded, output)['video_exact_match'])
            self.assertTrue(output.endswith(trailer))
            self.assertLess(next(i for i,e in enumerate(m.events) if e[0]=='sync'),
                            next(i for i,e in enumerate(m.events) if e[0]=='close' and e[1].endswith('.tmp')))

    def test_failure_never_publishes(self):
        for fail in ('missing_lrv','open_dest','read','write','seek','alloc','format','sync','close_dest','rename'):
            with self.subTest(fail=fail):
                m = self.run_payload(fail=fail)
                self.assertNotIn(m.path[:-4]+'.MP.jpg', m.files)


class OptimizedBackgroundIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_optimized()
        cls.image=(ROOT/'builds/offline-gallery-motion/main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def test_background_worker_produces_gallery_layout(self):
        folder=ROOT/'analysis/gallery-bitrate-trial-q-hardware'
        stem='LIV_20261029_152417_937'
        jpg=(folder/(stem+'.jpg')).read_bytes(); video=(folder/(stem+'.lrv')).read_bytes()
        trailer=jpg[jpeg_end(jpg):]
        m=WorkerMachine(image_data=self.image,jpeg=jpg,lrv=video,timestamp=1468)
        self.assertIsNone(m.run())
        self.assertEqual(m.step(),0)
        output=bytes(m.files[m.path[:-4]+'.MP.jpg'])
        check(jpg,video+struct.pack('>I4s',len(trailer)+8,b'free')+trailer,output)
        self.assertEqual(m.files[m.path],jpg)
        self.assertEqual(m.files[m.path[:-4]+'.lrv'],video)

    def test_optimized_image_only_changes_reserved_payload(self):
        from build_motion_candidate import CAVE
        from build_fast_copy_candidate import PAYLOAD_END
        from build_record_pool_diagnostic_candidate import DEST
        from build_usb_name_candidate import unpack_package
        import lz4.frame
        original=lz4.frame.decompress(unpack_package(DEST.read_bytes())['parts'][0]['payload'])
        self.assertEqual(self.image[:CAVE-BASE],original[:CAVE-BASE])
        self.assertEqual(self.image[PAYLOAD_END-BASE:],original[PAYLOAD_END-BASE:])

    def test_optimized_failures_keep_originals(self):
        for fail in ('missing_lrv','open_dest','read','write','seek','alloc','close_dest','rename'):
            with self.subTest(fail=fail):
                m=WorkerMachine(image_data=self.image,fail=fail)
                m.run();m.step()
                self.assertNotIn(m.path[:-4]+'.MP.jpg',m.files)
                self.assertEqual(m.files[m.path],m.jpeg)
                self.assertEqual(m.files[m.path[:-4]+'.lrv'],m.lrv)

    def test_packaged_image_matches_tested_image(self):
        import lz4.frame
        from build_gallery_motion_candidate import package, DEST
        from build_usb_name_candidate import unpack_package, USB_OFFSETS
        package()
        packaged=bytearray(lz4.frame.decompress(unpack_package(DEST.read_bytes())['parts'][0]['payload']))
        expected=bytearray(self.image)
        for offset in USB_OFFSETS:
            self.assertEqual(packaged[offset:offset+18],b'Insta360 Ace Pro t')
            expected[offset:offset+18]=b'Insta360 Ace Pro t'
        self.assertEqual(packaged,expected)

    def test_delete_guard_waits_while_a_worker_job_is_pending(self):
        import json
        from unicorn.arm64_const import UC_ARM64_REG_PC
        symbols=json.loads((ROOT/'builds/offline-background-save/build_report.json').read_text())['symbols']
        m=WorkerMachine(image_data=self.image,symbols=symbols)
        m.run()
        m.call('motion_worker_before_delete',0x50000000)
        self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),0x25ef40)
