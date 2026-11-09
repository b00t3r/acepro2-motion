"""Offline fault tests; callbacks are simulations, not camera I/O."""
import ctypes
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ctypes.c_char_p
RENAME=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,P,P)
MATCH=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,P,P)

class Ops(ctypes.Structure):
    _fields_=[('ctx',ctypes.c_void_p),('rename',RENAME),('matches',MATCH)]

class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion/rename-probe-test.dylib'
        out.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['clang','-dynamiclib','-O2',str(ROOT/'tools/rename_collision_probe.c'),'-o',str(out)],check=True)
        cls.probe=ctypes.CDLL(str(out)).rename_collision_probe
        cls.probe.argtypes=[ctypes.POINTER(Ops),ctypes.c_int]+[ctypes.POINTER(ctypes.c_int)]*4
        cls.probe.restype=ctypes.c_int

    def run_probe(self,armed=True,valid=True,overwrite=False):
        src=r'C:\CODEX_RENAME_PROBE\SOURCE.TST'; dst=r'C:\CODEX_RENAME_PROBE\DEST.TST'
        files={src:'CODEX-RENAME-SOURCE-7139',dst:'CODEX-RENAME-DEST-7139' if valid else 'unexpected'}
        calls=[]
        def match(_,path,content): return int(files.get(path.decode())==content.decode())
        def rename(_,a,b):
            calls.append((a.decode(),b.decode()))
            if not overwrite:return 0x110004
            files[b.decode()]=files.pop(a.decode());return 0
        refs=(RENAME(rename),MATCH(match));ops=Ops(None,*refs)
        values=[ctypes.c_int(-7) for _ in range(4)]
        rc=self.probe(ctypes.byref(ops),int(armed),*[ctypes.byref(x) for x in values])
        return rc,[x.value for x in values],calls

    def test_preconditions_prevent_rename(self):
        for kwargs in ({'armed':False},{'valid':False}):
            rc,_,calls=self.run_probe(**kwargs)
            self.assertEqual(rc,-1);self.assertEqual(calls,[])

    def test_both_collision_behaviors_are_observable(self):
        self.assertEqual(self.run_probe()[1],[0x110004,1,1,0])
        self.assertEqual(self.run_probe(overwrite=True)[1],[0,0,0,1])
