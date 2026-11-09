"""Offline ARM integration using simulated filesystem and verifier."""
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

class CameraCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion';out.mkdir(parents=True,exist_ok=True); objs=[]
        for name in ('motion_cleanup_camera.c','motion_cleanup_transaction.c'):
            obj=out/(name+'.o')
            subprocess.run(['clang','-target','aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                '-mgeneral-regs-only','-mno-outline-atomics','-c',str(ROOT/'tools'/name),'-o',str(obj)],check=True)
            objs.append(obj)
        cls.base=0x2558000;cls.stat=0x255a800;cls.verify=0x255a900
        blobs,sym,_=link_regions([(cls.base,0x255a000,objs)],{'motion_stat_detail':cls.stat,'motion_verify_camera':cls.verify})
        cls.blob=blobs[0];cls.entry=sym['motion_cleanup_camera']

    def run_case(self,error=None):
        h=Harness();u=h.uc;u.mem_write(self.base,self.blob)
        names=['jpg','motion','backup','lrv','mp4'];files={'jpg':'original','motion':'combined','lrv':'video','mp4':'main'}
        for i,n in enumerate(names):u.mem_write(CONTEXT+0x100+i*32,n.encode()+b'\0')
        # aarch64 struct: three u32, padding, two pointers.
        u.mem_write(CONTEXT+0x400,struct.pack('<III4xQQ',20,200,30,CONTEXT+0x800,CONTEXT+0x1000))
        u.reg_write(a.UC_ARM64_REG_X0,CONTEXT+0x400)
        for i in range(5):u.reg_write(getattr(a,'UC_ARM64_REG_X%d'%(i+1)),CONTEXT+0x100+i*32)
        events=[];count={'verify':0}
        def string(p):return bytes(u.mem_read(p,32)).split(b'\0',1)[0].decode()
        def stat(uc):
            n=string(uc.reg_read(a.UC_ARM64_REG_X0));code=0 if n in files else 3
            if error=='stat' and n=='backup':code=9
            uc.mem_write(uc.reg_read(a.UC_ARM64_REG_X1),struct.pack('<I',code));return 0 if code==0 else 2
        def rename(uc):
            src=string(uc.reg_read(a.UC_ARM64_REG_X0));dst=string(uc.reg_read(a.UC_ARM64_REG_X1));events.append(('rename',src,dst))
            if src not in files or dst in files:return 1
            files[dst]=files.pop(src);return 0
        def remove(uc):
            n=string(uc.reg_read(a.UC_ARM64_REG_X0));events.append(('delete',n))
            if n not in files:return 1
            del files[n];return 0
        def verify(uc):
            jpg,lrv,motion=[string(uc.reg_read(r)) for r in (a.UC_ARM64_REG_X0,a.UC_ARM64_REG_X1,a.UC_ARM64_REG_X2)]
            count['verify']+=1;events.append(('verify',jpg,lrv,motion))
            return int((error=='verify2' and count['verify']==2) or files.get(jpg)!='original' or files.get(lrv)!='video' or files.get(motion)!='combined')
        h.mocks={self.stat:stat,self.verify:verify,0x26aba0:rename,0x1077200:remove}
        h.run(self.entry)
        return u.reg_read(a.UC_ARM64_REG_X0)&0xffffffff,files,events

    def test_unknown_durability_prevents_all_deletion(self):
        rc,files,events=self.run_case()
        self.assertEqual(rc,2)
        self.assertEqual(files,{'jpg':'combined','backup':'original','lrv':'video','mp4':'main'})
        self.assertFalse(any(e[0]=='delete' for e in events))

    def test_unexpected_stat_and_failed_recheck_never_delete(self):
        for error in ('stat','verify2'):
            with self.subTest(error=error):
                rc,files,events=self.run_case(error)
                self.assertNotEqual(rc,0);self.assertFalse(any(e[0]=='delete' for e in events))
                self.assertIn('original',files.values())
