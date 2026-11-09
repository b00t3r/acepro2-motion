"""Host tests of the compiled queue core; no claim of native camera integration."""
import ctypes as c
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Job(c.Structure):
    _fields_=[('timestamp_ms',c.c_ulonglong),('filename',c.c_char*100)]


class Queue(c.Structure):
    _fields_=[(n,c.c_uint) for n in ('lock','closing','head','count','active')]+[
        ('queued',Job*2),('running',Job)]


class MotionQueueCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        root=Path(cls.temp.name)
        subprocess.run(['clang','-Os','-shared','-fPIC',str(ROOT/'tools/motion_queue_core.c'),
                        '-o',str(root/'queue.dylib')],check=True,capture_output=True)
        cls.lib=c.CDLL(str(root/'queue.dylib'))
        for name,args in {'submit':[c.POINTER(Queue),c.c_char_p,c.c_ulonglong],
                          'take':[c.POINTER(Queue),c.POINTER(Job)],
                          'finish':[c.POINTER(Queue)],'close':[c.POINTER(Queue)],
                          'pending':[c.POINTER(Queue),c.POINTER(c.c_uint)],
                          'resume':[c.POINTER(Queue)]}.items():
            fn=getattr(cls.lib,'motion_queue_'+name);fn.argtypes=args;fn.restype=c.c_int
        # Also ensure the same source compiles for the actual firmware ISA.
        subprocess.run(['clang','-target','aarch64-none-elf','-Os','-ffreestanding',
                        '-fno-builtin','-mgeneral-regs-only','-c',str(ROOT/'tools/motion_queue_core.c'),
                        '-o',str(root/'queue-aarch64.o')],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):self.q=Queue()
    def call(self,name,*args):return getattr(self.lib,'motion_queue_'+name)(c.byref(self.q),*args)
    def pending(self):
        n=c.c_uint();self.assertEqual(self.call('pending',c.byref(n)),0);return n.value

    def test_filename_and_timestamp_are_owned_by_job(self):
        name=c.create_string_buffer(b'C:\\DCIM\\Camera01\\LIV_first.jpg')
        self.assertEqual(self.call('submit',name,1434),0)
        name.value=b'C:\\DCIM\\Camera01\\LIV_second.jpg'
        job=Job();self.assertEqual(self.call('take',c.byref(job)),0)
        self.assertEqual(job.filename,b'C:\\DCIM\\Camera01\\LIV_first.jpg')
        self.assertEqual(job.timestamp_ms,1434)

    def test_capacity_counts_running_job_and_applies_backpressure(self):
        self.assertEqual(self.call('submit',b'first',1000),0)
        job=Job();self.assertEqual(self.call('take',c.byref(job)),0)
        self.assertEqual(self.call('submit',b'second',2000),0)
        self.assertEqual(self.call('submit',b'third',3000),3)
        self.assertEqual(self.pending(),2)
        self.assertEqual(self.call('finish'),0)
        self.assertEqual(self.call('submit',b'third',3000),0)
        for expected in (b'second',b'third'):
            self.assertEqual(self.call('take',c.byref(job)),0)
            self.assertEqual(job.filename,expected)
            self.assertEqual(self.call('finish'),0)
        self.assertEqual(self.pending(),0)

    def test_duplicate_callbacks_do_not_repeat_pending_work(self):
        self.assertEqual(self.call('submit',b'first',1434),0)
        self.assertEqual(self.call('submit',b'first',1434),4)
        job=Job();self.assertEqual(self.call('take',c.byref(job)),0)
        self.assertEqual(self.call('submit',b'first',1434),4)
        self.assertEqual(self.pending(),1)

    def test_storage_barrier_rejects_submissions_and_waits_for_running_job(self):
        self.assertEqual(self.call('submit',b'first',1434),0)
        job=Job();self.assertEqual(self.call('take',c.byref(job)),0)
        self.assertEqual(self.call('close'),0)
        self.assertEqual(self.call('submit',b'second',1401),2)
        self.assertEqual(self.call('resume'),7)
        self.assertEqual(self.pending(),1)
        self.assertEqual(self.call('finish'),0)
        self.assertEqual(self.pending(),0)
        self.assertEqual(self.call('resume'),0)
        self.assertEqual(self.call('submit',b'second',1401),0)

    def test_closed_queue_can_drain_remaining_jobs(self):
        self.assertEqual(self.call('submit',b'first',1434),0)
        self.assertEqual(self.call('submit',b'second',1401),0)
        self.assertEqual(self.call('close'),0)
        job=Job()
        for expected in (1434,1401):
            self.assertEqual(self.call('take',c.byref(job)),0)
            self.assertEqual(job.timestamp_ms,expected)
            self.assertEqual(self.call('finish'),0)
        self.assertEqual(self.pending(),0)
        self.assertEqual(self.call('take',c.byref(job)),6)

    def test_contention_returns_without_spinning_or_corrupting_jobs(self):
        self.q.lock=1
        job=Job();count=c.c_uint()
        for name,args in [('submit',(b'first',1434)),('take',(c.byref(job),)),
                          ('finish',()),('close',()),('resume',()),('pending',(c.byref(count),))]:
            self.assertEqual(self.call(name,*args),1)
        self.assertEqual(self.q.count,0)
        self.assertEqual(self.q.closing,0)
        self.q.lock=0
        self.assertEqual(self.call('submit',b'first',1434),0)

    def test_invalid_input_never_queues_a_truncated_name(self):
        for name,stamp in ((b'',1434),(b'A'*100,1434),(None,1434),(b'first',10001)):
            self.assertEqual(self.call('submit',name,stamp),5)
        self.assertEqual(self.pending(),0)

    def test_concurrent_producer_worker_and_storage_close(self):
        accepted=[];completed=[];errors=[];producer_done=threading.Event()
        def producer():
            try:
                for i in range(200):
                    name=('capture_%03d'%i).encode()
                    while True:
                        result=self.call('submit',name,i)
                        if result==0:
                            accepted.append((name,i));break
                        if result==2:return
                        if result not in (1,3):raise AssertionError(result)
                        time.sleep(0.0001)
            except BaseException as e:errors.append(e)
            finally:producer_done.set()
        def worker():
            try:
                job=Job()
                while True:
                    result=self.call('take',c.byref(job))
                    if result==0:
                        completed.append((job.filename,job.timestamp_ms))
                        time.sleep(0.0001)  # Simulate file work outside queue lock.
                        while self.call('finish')==1:time.sleep(0.0001)
                    elif result in (1,6):
                        if producer_done.is_set() and self.pending()==0:return
                        time.sleep(0.0001)
                    else:raise AssertionError(result)
            except BaseException as e:errors.append(e)
        a=threading.Thread(target=producer);b=threading.Thread(target=worker)
        a.start();b.start()
        time.sleep(0.005)
        while self.call('close')==1:time.sleep(0.0001)
        a.join(5);b.join(5)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(errors,[])
        self.assertTrue(accepted)
        self.assertEqual(completed,accepted)
        self.assertEqual(self.pending(),0)
