"""Run linked ARM worker code with scheduler APIs mocked, not a full RTOS."""
import json
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import *
from test_fast_copy_candidate import CountedMachine
from test_motion_candidate import ROOT
from build_background_prototype import OUT,WORKER_BASE,WORKER_END
from build_clean_motion_photo import capture_timestamp_ms

REPORT=json.loads((OUT/'build_report.json').read_text())
SYMS=REPORT['symbols']
IMAGE=(OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes()
WORK=0x50020000


class WorkerMachine(CountedMachine):
    def __init__(self,task_fail=False,resume_fail=False,image_data=None,symbols=None,**kwargs):
        self.workspace_allocations=0;self.creates=[];self.resume_fail=resume_fail
        self.symbols=SYMS if symbols is None else symbols
        super().__init__(image_data=IMAGE if image_data is None else image_data,native_format=True,**kwargs)
        self.uc.mem_map(WORK,0x20000)
        def create():
            self.creates.append([self.arg(i) for i in range(8)])
            return 1 if task_fail else 0
        for addr,fn in ((0x1248ac0,create),(0x1248f40,lambda:0),
                        (0x1248ca0,lambda:int(resume_fail))):
            self.uc.hook_add(UC_HOOK_CODE,self.callback(fn),begin=addr,end=addr)
        # Stop on sleep so tests can explicitly schedule the worker separately.
        self.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:uc.emu_stop(),begin=0x25ef40,end=0x25ef40)

    def alloc(self):
        if self.arg(1)==0x11000:
            self.workspace_allocations+=1
            if self.fail=='workspace_alloc':return 1
            self.uc.mem_write(self.arg(0),struct.pack('<Q',WORK))
            return 0
        return super().alloc()

    def call(self,name,*args,stack=0x70018000):
        self.uc.reg_write(UC_ARM64_REG_SP,stack)
        self.uc.reg_write(UC_ARM64_REG_X30,0x71000000)
        for reg,arg in zip(self.regs,args):self.uc.reg_write(reg,arg)
        self.uc.emu_start(self.symbols[name],0x71000000,count=80_000_000,timeout=30_000_000)
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def step(self):return self.call('motion_worker_step',WORK,stack=WORK+0x11000)


class BackgroundWorkerPrototypeTests(unittest.TestCase):
    def test_capture_returns_before_copy_then_worker_produces_motion_photo(self):
        m=WorkerMachine();self.assertIsNone(m.run())
        self.assertEqual(m.write_count,0)
        self.assertEqual(m.workspace_allocations,1)
        self.assertEqual(m.creates[0],[WORK,m.creates[0][1],100,
            SYMS['worker_entry'],WORK,WORK+0x1000,0x10000,0])
        self.assertEqual(m.step(),0)
        self.assertIn(m.path[:-4]+'.MP.jpg',m.files)
        self.assertEqual(m.files[m.path],m.jpeg)
        self.assertEqual(m.files[m.path[:-4]+'.lrv'],m.lrv)
        self.assertFalse(m.allocated or m.handles)

    def test_queued_snapshot_survives_changed_timestamp_filename_and_live_toggle(self):
        m=WorkerMachine(timestamp=1434);m.run()
        m.uc.mem_write(0x1262e904,struct.pack('<I',0))
        m.uc.mem_write(0x1264f320,struct.pack('<Q',9999))
        m.uc.mem_write(0x50000000,b'C:\\DCIM\\Camera01\\LIV_reused.jpg\0')
        self.assertEqual(m.step(),0)
        output=m.files[m.path[:-4]+'.MP.jpg']
        self.assertIn(b'Camera:MotionPhotoPresentationTimestampUs="1434000"',output)
        self.assertTrue(output.endswith(m.lrv))

    def test_failed_native_task_or_allocation_falls_back_to_synchronous_save(self):
        for kwargs in ({'task_fail':True},{'resume_fail':True},{'fail':'workspace_alloc'}):
            with self.subTest(kwargs=kwargs):
                m=WorkerMachine(**kwargs)
                self.assertIsNotNone(m.run())
                self.assertEqual(m.files[m.path],m.jpeg)
                self.assertFalse(m.allocated or m.handles)

    def test_storage_barrier_waits_for_copy_then_rejects_until_explicit_resume(self):
        m=WorkerMachine();m.run()
        m.call('motion_worker_quiesce')
        self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),0x25ef40)
        barrier_context=m.uc.context_save()
        self.assertEqual(m.step(),0)
        m.uc.context_restore(barrier_context)
        m.uc.reg_write(UC_ARM64_REG_PC,m.uc.reg_read(UC_ARM64_REG_X30))
        m.uc.emu_start(m.uc.reg_read(UC_ARM64_REG_PC),0x71000000,count=100000)
        self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),0x71000000)
        self.assertEqual(m.call('motion_submit',0x50000000,0),2)
        self.assertEqual(m.call('motion_worker_resume'),0)

    def test_worker_failure_releases_queue_slot_and_preserves_originals(self):
        m=WorkerMachine(fail='write');m.run();self.assertEqual(m.step(),0)
        self.assertNotIn(m.path[:-4]+'.MP.jpg',m.files)
        self.assertFalse(m.allocated or m.handles)
        self.assertEqual(m.call('motion_worker_quiesce'),0)
        self.assertEqual(m.call('motion_worker_resume'),0)
        self.assertEqual(m.files[m.path],m.jpeg)

    def test_actual_camera_files_retain_original_data_and_timing(self):
        folder=ROOT/'analysis/fast-copy-trial-r-hardware'
        for stem in ('LIV_20261029_153519_936','LIV_20261029_153526_937'):
            jpg=(folder/(stem+'.jpg')).read_bytes();lrv=(folder/(stem+'.lrv')).read_bytes()
            stamp=capture_timestamp_ms(jpg)
            m=WorkerMachine(jpeg=jpg,lrv=lrv,timestamp=stamp)
            m.run();self.assertEqual(m.step(),0)
            output=m.files[m.path[:-4]+'.MP.jpg']
            self.assertEqual(output,(folder/(stem+'.MP.jpg')).read_bytes())
