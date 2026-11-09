"""Fault-injection tests for the offline cleanup protocol; not camera I/O."""
import ctypes
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ctypes.c_char_p
PATH=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,P)
RENAME=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,P,P)
VERIFY=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,P,P,P)
BARRIER=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)


class Ops(ctypes.Structure):
    _fields_=[('context',ctypes.c_void_p),('exists',PATH),('rename_no_replace',RENAME),
              ('remove',PATH),('verify',VERIFY),('durable',BARRIER)]


class CleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'builds/offline-gallery-motion/cleanup-model.dylib'
        out.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['clang','-dynamiclib','-O2',str(ROOT/'tools/motion_cleanup_transaction.c'),'-o',str(out)],check=True)
        cls.run_core=ctypes.CDLL(str(out)).motion_cleanup_transaction
        cls.run_core.argtypes=[ctypes.POINTER(Ops),P,P,P,P,P]
        cls.run_core.restype=ctypes.c_int
        cls.restore=ctypes.CDLL(str(out)).motion_cleanup_restore_original
        cls.restore.argtypes=[ctypes.POINTER(Ops),P,P]
        cls.restore.restype=ctypes.c_int

    def run_case(self,fail=None,stale_backup=False,alias=False):
        files={'orig':b'original','motion':b'verified-motion','lrv':b'video','mp4':b'main'}
        if stale_backup: files['backup']=b'old-data'
        events=[]; counts={}
        def bad(op):
            counts[op]=counts.get(op,0)+1
            wanted=fail if isinstance(fail,set) else {fail}
            return (op,counts[op]) in wanted
        def exists(_,path):
            name=path.decode();events.append(('exists',name))
            return -1 if bad('exists') else int(name in files)
        def rename(_,a,b):
            a=a.decode();b=b.decode();events.append(('rename',a,b))
            if bad('rename') or a not in files or b in files:return 1
            files[b]=files.pop(a);events.append(('state',dict(files)));return 0
        def remove(_,path):
            name=path.decode();events.append(('remove',name))
            if bad('remove') or name not in files:return 1
            del files[name];events.append(('state',dict(files)));return 0
        def verify(_,m,j,v):
            m=m.decode();j=j.decode();v=v.decode();events.append(('verify',m,j,v))
            return int(bad('verify') or files.get(m)!=b'verified-motion' or
                       files.get(j)!=b'original' or files.get(v)!=b'video')
        def durable(_):events.append(('durable',));return int(bad('durable'))
        refs=[PATH(exists),RENAME(rename),PATH(remove),VERIFY(verify),BARRIER(durable)]
        ops=Ops(None,*refs)
        result=self.run_core(ctypes.byref(ops),b'orig',b'motion',b'backup',b'lrv',b'orig' if alias else b'mp4')
        return result,files,events

    def test_success_leaves_one_verified_file(self):
        result,files,_=self.run_case()
        self.assertEqual(result,0)
        self.assertEqual(files,{'orig':b'verified-motion'})

    def test_failures_never_lose_both_photo_representations(self):
        for op,total in (('exists',5),('verify',2),('rename',2),('durable',1),('remove',3)):
            for n in range(1,total+1):
                with self.subTest(op=op,n=n):
                    result,files,events=self.run_case((op,n))
                    self.assertNotEqual(result,0)
                    self.assertTrue(any(v in (b'original',b'verified-motion') for v in files.values()))
                    if op in ('exists','verify','rename','durable'):
                        self.assertFalse(any(e[0]=='remove' for e in events))

    def test_backup_collision_and_alias_abort_without_mutation(self):
        for kw in ({'stale_backup':True},{'alias':True}):
            result,files,events=self.run_case(**kw)
            self.assertEqual(result,1)
            self.assertFalse(any(e[0] in ('rename','remove') for e in events))

    def test_each_mutation_leaves_photo_data_available(self):
        for fail in (None,('verify',2),('remove',1),{('rename',2),('rename',3)}):
            _,_,events=self.run_case(fail)
            for event in events:
                if event[0]=='state':
                    self.assertTrue(any(v in (b'original',b'verified-motion') for v in event[1].values()))

    def test_failed_replace_and_failed_restore_keep_both_files(self):
        result,files,_=self.run_case({('rename',2),('rename',3)})
        self.assertEqual(result,2)
        self.assertEqual(files['backup'],b'original')
        self.assertEqual(files['motion'],b'verified-motion')

    def test_restore_only_when_original_definitely_missing(self):
        for original,backup,exists_error,rename_error,expected,changed in (
                (False,True,False,False,0,True),
                (True,True,False,False,0,False),
                (False,False,False,False,1,False),
                (False,True,True,False,1,False),
                (False,True,False,True,2,False)):
            with self.subTest(original=original,backup=backup,error=exists_error,rename=rename_error):
                files={}
                if original:files['orig']=b'existing'
                if backup:files['backup']=b'original'
                def exists(_,p):return -1 if exists_error else int(p.decode() in files)
                def rename(_,a,b):
                    if rename_error or a.decode() not in files or b.decode() in files:return 1
                    files[b.decode()]=files.pop(a.decode());return 0
                refs=[PATH(exists),RENAME(rename),PATH(lambda *_:1),VERIFY(lambda *_:1),BARRIER(lambda *_:1)]
                ops=Ops(None,*refs)
                self.assertEqual(self.restore(ctypes.byref(ops),b'orig',b'backup'),expected)
                self.assertEqual(files.get('orig')==b'original',changed)
                if original:self.assertEqual(files['orig'],b'existing')

    def test_interruption_after_each_mutation_keeps_recoverable_photo(self):
        _,_,events=self.run_case()
        snapshots=[event[1] for event in events if event[0]=='state']
        self.assertEqual(len(snapshots),5)
        for i,snapshot in enumerate(snapshots):
            with self.subTest(after_mutation=i+1):
                files=dict(snapshot)
                def exists(_,p):return int(p.decode() in files)
                def rename(_,a,b):
                    src=a.decode();dst=b.decode()
                    if src not in files or dst in files:return 1
                    files[dst]=files.pop(src);return 0
                refs=[PATH(exists),RENAME(rename),PATH(lambda *_:1),VERIFY(lambda *_:1),BARRIER(lambda *_:1)]
                ops=Ops(None,*refs)
                self.assertEqual(self.restore(ctypes.byref(ops),b'orig',b'backup'),0)
                self.assertIn(files.get('orig'),(b'original',b'verified-motion'))
