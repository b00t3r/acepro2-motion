"""ARM adapter tests with simulated filesystem; no device operations."""
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unicorn import arm64_const as a
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_background_prototype import link_regions
from livephoto_harness import Harness,CONTEXT

class CameraProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion';out.mkdir(parents=True,exist_ok=True)
        objs=[]
        for name in ('rename_collision_camera.c','rename_collision_probe.c'):
            obj=out/(name+'.o')
            subprocess.run(['clang','-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                '-mgeneral-regs-only','-mno-outline-atomics','-c',str(ROOT/'tools'/name),'-o',str(obj)],check=True)
            objs.append(obj)
        cls.base=0x2558000
        blobs,symbols,_=link_regions([(cls.base,cls.base+0x2000,objs)])
        cls.blob=blobs[0];cls.entry=symbols['rename_collision_camera_probe']

    def run_probe(self,armed=True,valid=True,overwrite=False,repeat=False):
        h=Harness();u=h.uc;u.mem_write(self.base,self.blob)
        prefix='C:\\CODEX_RENAME_PROBE\\'
        files={prefix+'ARM.TST':b'CODEX-RENAME-ARM-7139',
               prefix+'SOURCE.TST':b'CODEX-RENAME-SOURCE-7139',
               prefix+'DEST.TST':b'CODEX-RENAME-DEST-7139' if valid else b'wrong'}
        if not armed:del files[prefix+'ARM.TST']
        calls=[];handles={};logs=[]
        def string(p):return bytes(u.mem_read(p,128)).split(b'\0',1)[0].decode()
        def open_(uc):
            path=string(uc.reg_read(a.UC_ARM64_REG_X0));mode=string(uc.reg_read(a.UC_ARM64_REG_X1))
            calls.append(('open',path,mode))
            if path not in files:return 1
            handle=CONTEXT+0x500+len(handles)*16;handles[handle]=path
            uc.mem_write(uc.reg_read(a.UC_ARM64_REG_X2),struct.pack('<Q',handle));return 0
        def read(uc):
            path=handles[uc.reg_read(a.UC_ARM64_REG_X3)]
            data=files[path][:uc.reg_read(a.UC_ARM64_REG_X2)]
            uc.mem_write(uc.reg_read(a.UC_ARM64_REG_X0),data);return len(data)
        def close(uc):return 0
        def rename(uc):
            src=string(uc.reg_read(a.UC_ARM64_REG_X0));dst=string(uc.reg_read(a.UC_ARM64_REG_X1))
            calls.append(('rename',src,dst))
            if not overwrite:return 0x110004
            files[dst]=files.pop(src);return 0
        def log(uc):
            logs.append([uc.reg_read(getattr(a,'UC_ARM64_REG_X%d'%i))&0xffffffff for i in range(4,8)]);return 0
        h.mocks={0x26a860:open_,0x26a960:read,0x26a8a0:close,0x26aba0:rename,0x71b880:log}
        h.run(self.entry)
        if repeat: h.run(self.entry)
        return calls,files,logs

    def test_marker_and_contents_gate_rename(self):
        for kwargs in ({'armed':False},{'valid':False}):
            calls,_,_=self.run_probe(**kwargs)
            self.assertFalse(any(c[0]=='rename' for c in calls))
            self.assertTrue(all(c[2]=='rb' for c in calls if c[0]=='open'))

    def test_collision_simulations(self):
        for overwrite in (False,True):
            calls,files,_=self.run_probe(overwrite=overwrite)
            self.assertEqual(sum(c[0]=='rename' for c in calls),1)
            self.assertEqual(any(k.endswith('SOURCE.TST') for k in files),not overwrite)

    def test_second_invocation_does_not_repeat_rename(self):
        calls,_,_=self.run_probe(repeat=True)
        self.assertEqual(sum(c[0]=='rename' for c in calls),1)
