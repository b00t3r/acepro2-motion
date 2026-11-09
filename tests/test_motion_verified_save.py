"""Exercise the integrated ARM save, sync and read-back path in emulation.

The large helper region is an emulator-only address; no update is produced.
"""
import subprocess
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_SP,UC_ARM64_REG_X0,UC_ARM64_REG_X30
from test_background_worker_prototype import WorkerMachine,WORK
from build_background_prototype import link_regions
from build_gallery_motion_offline import build
from livephoto_geometry_patch import branch
from livephoto_harness import BASE
from make_motion_photo import jpeg_end
from verify_device_motion_photo import check
import struct

ROOT=Path(__file__).resolve().parents[1]
TEST_REGION=0x2558000
SAVE_ENTRY=0x502bc


class CorruptReadbackWorker(WorkerMachine):
    def __init__(self,*args,corrupt=False,sync_fail=False,**kwargs):
        self.corrupt_readback=corrupt
        self.sync_fail=sync_fail
        self.sync_calls=0
        super().__init__(*args,**kwargs)
        def sync():
            self.sync_calls+=1
            return int(self.sync_fail)
        self.uc.hook_add(UC_HOOK_CODE,self.callback(sync),begin=0x26aa80,end=0x26aa80)

    def step(self):
        self.uc.reg_write(UC_ARM64_REG_SP,WORK+0x11000)
        self.uc.reg_write(UC_ARM64_REG_X30,0x71000000)
        self.uc.reg_write(UC_ARM64_REG_X0,WORK)
        self.uc.emu_start(self.symbols['motion_worker_step'],0x71000000,
                          count=500000000,timeout=50000000)
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def open(self):
        path,mode=self.string(self.arg(0)),self.string(self.arg(1))
        if self.corrupt_readback and mode=='rb' and path.endswith('.MP.tmp') and path in self.files:
            data=bytearray(self.files[path]);data[-1]^=1;self.files[path]=data
        return super().open()


class VerifiedSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()
        out=ROOT/'builds/offline-gallery-motion'
        flags=['-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-fno-jump-tables','-mgeneral-regs-only','-mno-outline-atomics']
        objects=[]
        for name,defines in (
          ('motion_photo_payload',['-DMOTION_CAPTURED_TIMESTAMP','-DMOTION_COPY_BYTES=65536',
                                   '-DMOTION_GALLERY_TRAILER','-DMOTION_DURABLE_SAVE','-DMOTION_VERIFY_AFTER_SAVE']),
          ('motion_verify_camera',[]),('motion_verify_core',[])):
            obj=out/(name+'-integrated-test.o')
            subprocess.run(['clang',*flags,*defines,'-c',str(ROOT/'tools'/(name+'.c')),'-o',str(obj)],check=True)
            objects.append(obj)
        blobs,symbols,_=link_regions([(TEST_REGION,TEST_REGION+0x5000,objects)])
        data=bytearray((out/'main_threadx_OFFLINE_ONLY.bin').read_bytes())
        data[TEST_REGION-BASE:TEST_REGION-BASE+len(blobs[0])]=blobs[0]
        data[SAVE_ENTRY-BASE:SAVE_ENTRY-BASE+4]=branch(SAVE_ENTRY,symbols['motion_save_captured'])
        cls.image=bytes(data)
        p=ROOT/'analysis/gallery-motion-trial-t3';s='LIV_20261031_230615_943'
        cls.jpg=(p/(s+'.jpg')).read_bytes();cls.lrv=(p/(s+'.lrv')).read_bytes()

    def capture(self,**kwargs):
        m=CorruptReadbackWorker(image_data=self.image,jpeg=self.jpg,lrv=self.lrv,timestamp=1468,**kwargs)
        m.run();self.assertEqual(m.step(),0)
        self.assertFalse(m.handles);self.assertFalse(m.allocated)
        self.assertEqual(m.files[m.path],self.jpg)
        self.assertEqual(m.files[m.path[:-4]+'.lrv'],self.lrv)
        return m

    def test_verified_file_is_published(self):
        m=self.capture();out=bytes(m.files[m.path[:-4]+'.MP.jpg'])
        trailer=self.jpg[jpeg_end(self.jpg):]
        check(self.jpg,self.lrv+struct.pack('>I4s',len(trailer)+8,b'free')+trailer,out)
        self.assertEqual(m.sync_calls,1)

    def test_sync_or_readback_failure_does_not_publish(self):
        for options in ({'sync_fail':True},{'corrupt':True}):
            with self.subTest(**options):
                m=self.capture(**options)
                self.assertNotIn(m.path[:-4]+'.MP.jpg',m.files)
