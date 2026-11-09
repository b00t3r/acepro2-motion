"""Execute the real ARM camera-file adapter with mocked file services."""
import subprocess
import unittest
from pathlib import Path
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7,UC_ARM64_REG_X30
from test_fast_copy_candidate import CountedMachine, images
from build_background_prototype import link_regions
from livephoto_harness import BASE
from make_motion_photo import jpeg_end

ROOT=Path(__file__).resolve().parents[1]
ENTRY=0x2558000  # Emulator only, not an audited firmware location.


class CameraVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion';out.mkdir(parents=True,exist_ok=True)
        flags=['-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics']
        objects=[]
        for name in ('motion_verify_camera','motion_verify_core'):
            obj=out/(name+'-test.o')
            subprocess.run(['clang',*flags,'-c',str(ROOT/'tools'/(name+'.c')),'-o',str(obj)],check=True)
            objects.append(obj)
        blobs,symbols,_=link_regions([(ENTRY,ENTRY+0x3000,objects)])
        cls.entry=symbols['motion_verify_camera']
        image=bytearray(images()[1]);image[ENTRY-BASE:ENTRY-BASE+len(blobs[0])]=blobs[0]
        cls.image=bytes(image)
        p=ROOT/'analysis/gallery-motion-trial-t3';s='LIV_20261031_230615_943'
        cls.jpg=(p/(s+'.jpg')).read_bytes();cls.lrv=(p/(s+'.lrv')).read_bytes();cls.motion=(p/(s+'.MP.jpg')).read_bytes()
        cls.exif_end=4+int.from_bytes(cls.jpg[4:6],'big')
        n=2+int.from_bytes(cls.motion[cls.exif_end+2:cls.exif_end+4],'big')
        cls.xmp=cls.motion[cls.exif_end:cls.exif_end+n]

    def verify(self,motion=None,fail=None):
        path='C:\\DCIM\\Camera01\\LIV_20261027_200749_030.MP.jpg'
        m=CountedMachine(image_data=self.image,jpeg=self.jpg,lrv=self.lrv,
                         existing={path:self.motion if motion is None else motion},fail=fail)
        lrv_path=m.path[:-4]+'.lrv'
        m.uc.mem_write(0x50000400,lrv_path.encode()+b'\0')
        m.uc.mem_write(0x50000800,path.encode()+b'\0')
        m.uc.mem_write(0x50014000,self.xmp)
        for reg,val in zip((UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,
                            UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7),
                           (0x50000000,0x50000400,0x50000800,self.exif_end,jpeg_end(self.jpg),
                            0x50014000,len(self.xmp),0x50016000)):
            m.uc.reg_write(reg,val)
        m.uc.reg_write(UC_ARM64_REG_X30,0x71000000)
        m.uc.emu_start(self.entry,0x71000000,count=80000000,timeout=30000000)
        self.assertFalse(m.handles)
        for name,contents in m.originals.items():self.assertEqual(m.files[name],contents)
        return m.uc.reg_read(UC_ARM64_REG_X0)

    def test_real_capture_and_file_errors(self):
        self.assertEqual(self.verify(),0)
        for fail in ('missing_lrv','read','seek'):
            with self.subTest(fail=fail): self.assertNotEqual(self.verify(fail=fail),0)

    def test_corrupted_or_incomplete_output_rejected(self):
        bad=bytearray(self.motion);bad[-100]^=1
        self.assertNotEqual(self.verify(motion=bytes(bad)),0)
        self.assertNotEqual(self.verify(motion=self.motion[:-50]),0)
