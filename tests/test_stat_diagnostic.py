"""Run the actual ARM read-only diagnostic with mocked filesystem services."""
import sys
import unittest
import struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unicorn.arm64_const as arm
from unicorn.arm64_const import (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,
    UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6)
from build_stat_diagnostic_offline import build,OUT,STATE,CONFIG_HOOK
from livephoto_harness import Harness,CONTEXT


class StatDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=build();cls.image=(OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def run_case(self,resource=227,marker=True,close_error=False):
        h=Harness(self.image);uc=h.uc;calls=[];logs=[];paths=[]
        uc.mem_write(STATE,b'\0')
        def readstr(p):return bytes(uc.mem_read(p,128)).split(b'\0',1)[0].decode()
        def open_file(uc):
            calls.append(('open',readstr(uc.reg_read(UC_ARM64_REG_X0)),readstr(uc.reg_read(UC_ARM64_REG_X1))))
            if not marker:return 1
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X2),(CONTEXT+0x500).to_bytes(8,'little'))
            return 0
        def close_file(uc):calls.append(('close',));return int(close_error)
        def convert(uc):
            paths.append(readstr(uc.reg_read(UC_ARM64_REG_X1)))
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X0),bytes(24));return 0
        def stat(uc):return (0,49,9)[len(paths)-1]
        def log(uc):logs.append(tuple(uc.reg_read(r) for r in (UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6)));return 0
        h.mocks={0x26a860:open_file,0x26a8a0:close_file,0x14e1780:convert,
                 0x14ebd40:stat,0x71b880:log}
        uc.reg_write(UC_ARM64_REG_X0,resource);uc.reg_write(UC_ARM64_REG_X1,0)
        h.run(self.report['symbols']['fullsensor_marker_enabled'])
        return dict(armed=bytes(uc.mem_read(STATE,1))[0],calls=calls,paths=paths,logs=logs)

    def test_marker_gates_three_read_only_queries(self):
        r=self.run_case();self.assertEqual(r['armed'],1)
        self.assertEqual(r['calls'],[('open','C:\\RAW8K.ENABLE','rb'),('close',)])
        self.assertEqual(r['paths'],['C:\\RAW8K.ENABLE','C:\\CODEX_STAT_MISSING_4271.TST',
                                     'Z:\\CODEX_STAT_MISSING_4271.TST'])
        self.assertEqual(r['logs'],[(0,0,0),(1,2,49),(2,2,9)])

    def test_marker_errors_and_other_resources_do_not_query(self):
        for kwargs in ({'marker':False},{'close_error':True},{'resource':226}):
            with self.subTest(**kwargs):
                r=self.run_case(**kwargs);self.assertEqual(r['armed'],0)
                self.assertEqual(r['paths'],[]);self.assertEqual(r['logs'],[])

    def test_config_hook_preserves_state_when_services_clobber_registers(self):
        h=Harness(self.image);uc=h.uc;cfg=CONTEXT+0x1000
        regs=[getattr(arm,'UC_ARM64_REG_X%d'%i) for i in range(31)]
        vectors=[getattr(arm,'UC_ARM64_REG_Q%d'%i) for i in range(32)]
        for i,r in enumerate(regs):uc.reg_write(r,0x12340000+i)
        for i,r in enumerate(vectors):uc.reg_write(r,(i+1)*0x123456789abcdef)
        uc.mem_write(cfg+6,struct.pack('<HHH',227,30,0))
        uc.reg_write(arm.UC_ARM64_REG_X0,30);uc.reg_write(arm.UC_ARM64_REG_X19,cfg)
        uc.reg_write(arm.UC_ARM64_REG_NZCV,0xa0000000)
        before=[uc.reg_read(r) for r in regs];qbefore=[uc.reg_read(r) for r in vectors]
        sp=uc.reg_read(arm.UC_ARM64_REG_SP)
        def clobber(uc):
            for r in regs[1:19]:uc.reg_write(r,0xdeadbeef)
            for r in vectors:uc.reg_write(r,0)
            uc.reg_write(arm.UC_ARM64_REG_NZCV,0)
        def open_file(uc):
            uc.mem_write(uc.reg_read(arm.UC_ARM64_REG_X2),struct.pack('<Q',CONTEXT+0x500));clobber(uc);return 0
        def convert(uc):
            uc.mem_write(uc.reg_read(arm.UC_ARM64_REG_X0),bytes(24));clobber(uc);return 0
        def other(uc):clobber(uc);return 0
        h.mocks={0x26a860:open_file,0x26a8a0:other,0x14e1780:convert,0x14ebd40:other,0x71b880:other}
        h.stops={CONFIG_HOOK+4:'native_continuation'};h.run(CONFIG_HOOK)
        self.assertEqual([uc.reg_read(r) for r in regs],before)
        self.assertEqual([uc.reg_read(r) for r in vectors],qbefore)
        self.assertEqual(uc.reg_read(arm.UC_ARM64_REG_NZCV),0xa0000000)
        self.assertEqual(uc.reg_read(arm.UC_ARM64_REG_SP),sp)

    def test_packaged_candidate_contains_only_audited_changes(self):
        import lz4.frame
        from build_stat_diagnostic_candidate import package,DEST,SOURCE
        from build_stat_diagnostic_offline import HOOK,STUB,END,STOP_HOOK
        from build_usb_name_candidate import unpack_package,USB_OFFSETS
        from livephoto_harness import BASE
        package()
        before=lz4.frame.decompress(unpack_package(SOURCE.read_bytes())['parts'][0]['payload'])
        after=lz4.frame.decompress(unpack_package(DEST.read_bytes())['parts'][0]['payload'])
        allowed=set(range(STUB-BASE,END-BASE))
        for addr in (HOOK,CONFIG_HOOK,STOP_HOOK):allowed.update(range(addr-BASE,addr-BASE+4))
        for off in USB_OFFSETS:allowed.update(range(off,off+18))
        unexpected=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b and i not in allowed]
        self.assertFalse(unexpected)
        self.assertEqual(len(before),len(after))
        self.assertEqual(unpack_package(SOURCE.read_bytes())['parts'][1:],unpack_package(DEST.read_bytes())['parts'][1:])
