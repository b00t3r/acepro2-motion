"""Fault injection against real capture bytes; native camera APIs are mocked."""
import ctypes
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from make_motion_photo import jpeg_end

SEEK=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulonglong)
READ=ctypes.CFUNCTYPE(ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint)
SIZE=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulonglong))
class IO(ctypes.Structure):
    _fields_=[('ctx',ctypes.c_void_p),('seek',SEEK),('read',READ),('size',SIZE)]


class VerifyCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion/verify-model.dylib'
        out.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['clang','-dynamiclib','-O2',str(ROOT/'tools/motion_verify_core.c'),'-o',str(out)],check=True)
        cls.verify=ctypes.CDLL(str(out)).motion_verify_complete
        cls.verify.argtypes=[ctypes.POINTER(IO),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
            ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p]
        cls.verify.restype=ctypes.c_int
        p=ROOT/'analysis/gallery-motion-trial-t3';s='LIV_20261031_230615_943'
        cls.jpg=(p/(s+'.jpg')).read_bytes();cls.lrv=(p/(s+'.lrv')).read_bytes();cls.motion=(p/(s+'.MP.jpg')).read_bytes()
        cls.exif_end=4+int.from_bytes(cls.jpg[4:6],'big');cls.jpeg_end=jpeg_end(cls.jpg)
        n=2+int.from_bytes(cls.motion[cls.exif_end+2:cls.exif_end+4],'big')
        cls.xmp=cls.motion[cls.exif_end:cls.exif_end+n]

    def run_verify(self,motion=None,jpg=None,lrv=None,fail=None):
        files={1:self.jpg if jpg is None else jpg,2:self.lrv if lrv is None else lrv,
               3:self.motion if motion is None else motion}
        pos={1:0,2:0,3:0}; calls={'read':0}
        def seek(_,h,n):
            if fail=='seek': return 1
            pos[h]=n;return 0
        def read(_,h,dest,n):
            calls['read']+=1;data=files[h][pos[h]:pos[h]+n]
            if fail=='read' and calls['read']==3:data=data[:-1]
            if data:ctypes.memmove(dest,data,len(data))
            pos[h]+=len(data);return len(data)
        def size(_,h,dest):
            if fail=='size':return 1
            dest[0]=len(files[h]);return 0
        refs=[SEEK(seek),READ(read),SIZE(size)];io=IO(None,*refs)
        xmp=ctypes.create_string_buffer(self.xmp);buf=ctypes.create_string_buffer(8192)
        return self.verify(ctypes.byref(io),1,2,3,self.exif_end,self.jpeg_end,xmp,len(self.xmp),buf)

    def test_original_capture_and_io_failures(self):
        self.assertEqual(self.run_verify(),0)
        for fail in ('seek','read','size'):
            with self.subTest(fail=fail):self.assertNotEqual(self.run_verify(fail=fail),0)

    def test_corruption_in_every_segment_is_rejected(self):
        indices=[10,self.exif_end+20,self.exif_end+len(self.xmp)+100,
                 len(self.jpg)+len(self.xmp)+100,len(self.motion)-1]
        for index in indices:
            with self.subTest(index=index):
                damaged=bytearray(self.motion);damaged[index]^=1
                self.assertNotEqual(self.run_verify(motion=bytes(damaged)),0)
        self.assertNotEqual(self.run_verify(motion=self.motion[:-1]),0)
