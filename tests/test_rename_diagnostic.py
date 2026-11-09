"""Test packaged ARM diagnostic with simulated filesystem; no hardware I/O."""
import sys
import struct
import unittest
from pathlib import Path
from unicorn import arm64_const as a
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_rename_diagnostic import build,OUT
from livephoto_harness import Harness,CONTEXT

class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=build();cls.image=(OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def run_case(self,armed=True,valid=True,overwrite=False,resource=227,repeat=False,read_failure=False):
        h=Harness(self.image);u=h.uc; prefix='C:\\CXR7139\\'
        files={prefix+'A.TST':b'CODEX7139-A',prefix+'S.TST':b'CODEX7139-S',prefix+'D.TST':b'CODEX7139-D' if valid else b'wrong'}
        if not armed:del files[prefix+'A.TST']
        handles={};calls=[];logs=[]
        def string(p):return bytes(u.mem_read(p,128)).split(b'\0',1)[0].decode()
        def op(uc):
            path=string(uc.reg_read(a.UC_ARM64_REG_X0)); mode=string(uc.reg_read(a.UC_ARM64_REG_X1));calls.append(('open',path,mode))
            if path not in files:return 1
            handle=CONTEXT+0x500+len(handles)*16;handles[handle]=path
            uc.mem_write(uc.reg_read(a.UC_ARM64_REG_X2),struct.pack('<Q',handle));return 0
        def read(uc):
            data=files[handles[uc.reg_read(a.UC_ARM64_REG_X3)]][:uc.reg_read(a.UC_ARM64_REG_X2)]
            if read_failure:data=data[:2]
            if data:uc.mem_write(uc.reg_read(a.UC_ARM64_REG_X0),data)
            return len(data)
        def rename(uc):
            src=string(uc.reg_read(a.UC_ARM64_REG_X0));dst=string(uc.reg_read(a.UC_ARM64_REG_X1));calls.append(('rename',src,dst))
            if not overwrite:return 0x110004
            files[dst]=files.pop(src);return 0
        def delete(uc):
            path=string(uc.reg_read(a.UC_ARM64_REG_X0));calls.append(('delete',path))
            if path not in files:return 0x110004
            del files[path];return 0
        def log(uc):
            logs.append([uc.reg_read(getattr(a,'UC_ARM64_REG_X%d'%i))&0xffffffff for i in range(4,8)]);return 0
        h.mocks={0x26a860:op,0x26a960:read,0x26a8a0:lambda uc:0,0x26aba0:rename,0x1077200:delete,0x71b880:log}
        def invoke():
            u.reg_write(a.UC_ARM64_REG_X0,resource);u.reg_write(a.UC_ARM64_REG_X1,0)
            h.run(self.report['symbols']['fullsensor_marker_enabled'])
        invoke()
        if repeat:invoke()
        return calls,logs

    def test_gates_and_failures_do_not_rename(self):
        for opts in ({'armed':False},{'valid':False},{'resource':226},{'read_failure':True}):
            with self.subTest(**opts):
                calls,_=self.run_case(**opts)
                self.assertFalse(any(c[0]=='rename' for c in calls))
                self.assertTrue(all(c[2]=='rb' for c in calls if c[0]=='open'))

    def test_collision_results_and_one_attempt(self):
        for overwrite,expected in ((False,[0x110004,1,1,0]),(True,[0,0xffffffff,0,1])):
            with self.subTest(overwrite=overwrite):
                calls,logs=self.run_case(overwrite=overwrite,repeat=True)
                self.assertEqual(sum(c[0]=='rename' for c in calls),1)
                self.assertEqual(logs,[expected])

    def test_config_hook_preserves_registers_and_flags(self):
        from probe_guarded_fullsensor import HOOK
        h=Harness(self.image);u=h.uc;cfg=CONTEXT+0x1000
        regs=[getattr(a,'UC_ARM64_REG_X%d'%i) for i in range(31)]
        vectors=[getattr(a,'UC_ARM64_REG_Q%d'%i) for i in range(32)]
        for i,r in enumerate(regs):u.reg_write(r,0x12340000+i)
        for i,r in enumerate(vectors):u.reg_write(r,(i+1)*0x123456789abcdef)
        u.mem_write(cfg+6,struct.pack('<HHH',227,30,0))
        u.reg_write(a.UC_ARM64_REG_X0,30);u.reg_write(a.UC_ARM64_REG_X19,cfg)
        u.reg_write(a.UC_ARM64_REG_NZCV,0xa0000000)
        before=[u.reg_read(r) for r in regs];qbefore=[u.reg_read(r) for r in vectors]
        sp=u.reg_read(a.UC_ARM64_REG_SP)
        def fail_open(uc):
            for r in regs[1:19]:uc.reg_write(r,0xdeadbeef)
            for r in vectors:uc.reg_write(r,0)
            uc.reg_write(a.UC_ARM64_REG_NZCV,0)
            return 1
        h.mocks={0x26a860:fail_open};h.stops={HOOK+4:'native_continuation'};h.run(HOOK)
        self.assertEqual([u.reg_read(r) for r in regs],before)
        self.assertEqual([u.reg_read(r) for r in vectors],qbefore)
        self.assertEqual(u.reg_read(a.UC_ARM64_REG_NZCV),0xa0000000)
        self.assertEqual(u.reg_read(a.UC_ARM64_REG_SP),sp)
