import struct
import sys
import unittest
from pathlib import Path
import unicorn.arm64_const as arm
from unicorn.arm64_const import (UC_ARM64_REG_X0,UC_ARM64_REG_X2,UC_ARM64_REG_X9,UC_ARM64_REG_X10,
                                  UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X19,UC_ARM64_REG_X21,UC_ARM64_REG_X22,
                                  UC_ARM64_REG_SP,UC_ARM64_REG_NZCV)

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_raw_8k_diagnostic_offline import build,HOOK,CONFIG_HOOK,OUT,STATE
from livephoto_harness import CONTEXT,Harness


class DiagnosticHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()
        cls.data=(OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes()

    def test_scoped_gate_and_preservation(self):
        for width,flag,expected in ((4096,0,'normal'),(5999,0,'normal'),(6000,0,'debug'),
                                    (7680,0,'debug'),(4096,4,'debug')):
            h=Harness(self.data)
            h.uc.mem_write(STATE,b'\x01')
            h.uc.mem_write(CONTEXT+0x16,struct.pack('<H',width))
            h.uc.reg_write(UC_ARM64_REG_X21,CONTEXT)
            h.uc.reg_write(UC_ARM64_REG_X0,flag)
            h.uc.reg_write(UC_ARM64_REG_X9,0x123456789)
            h.uc.reg_write(UC_ARM64_REG_X10,0xabcdef123)
            h.uc.reg_write(UC_ARM64_REG_NZCV,0xa0000000)
            sp=h.uc.reg_read(UC_ARM64_REG_SP)
            h.stops={0x276f60:'normal',0x276fa4:'debug'}
            h.run(HOOK)
            self.assertEqual(h.outcome,expected)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X0),flag)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X9),0x123456789)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X10),0xabcdef123)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_NZCV),0xa0000000)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP),sp)

    def test_first_wide_frame_reaches_native_logger(self):
        h=Harness(self.data)
        h.uc.mem_map(0x120a3000,0x1000)
        h.uc.mem_map(0x12043000,0x1000)
        h.uc.mem_write(0x12043a08,struct.pack('<I',1))
        h.uc.mem_write(STATE,b'\x01')
        h.uc.mem_write(CONTEXT+0x16,struct.pack('<H',7680))
        h.uc.mem_write(CONTEXT+0x18,struct.pack('<H',4320))
        h.uc.reg_write(UC_ARM64_REG_X21,CONTEXT)
        h.uc.reg_write(UC_ARM64_REG_X22,CONTEXT+0x100)
        h.uc.reg_write(UC_ARM64_REG_X0,0)
        h.mocks={0x2639a0:lambda uc:0}
        h.stops={0x276f60:'normal',0x71b880:'native_logger'}
        h.run(HOOK)
        self.assertEqual(h.outcome,'native_logger')
        self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X0),5)
        fmt=bytes(h.uc.mem_read(h.uc.reg_read(UC_ARM64_REG_X3),250))
        self.assertIn(b'[LV_RAW]',fmt)
        self.assertEqual(struct.unpack('<Q',h.uc.mem_read(0x120a3c88,8))[0],1)
        sp=h.uc.reg_read(UC_ARM64_REG_SP)
        self.assertEqual(struct.unpack('<I',h.uc.mem_read(sp+0x28,4))[0],7680)
        self.assertEqual(struct.unpack('<I',h.uc.mem_read(sp+0x30,4))[0],4320)

    def test_existing_sampling_skips_second_event(self):
        h=Harness(self.data)
        h.uc.mem_map(0x120a3000,0x1000)
        h.uc.mem_write(0x120a3c88,struct.pack('<Q',1))
        h.uc.mem_write(STATE,b'\x01')
        h.uc.mem_write(CONTEXT+0x16,struct.pack('<H',7680))
        h.uc.reg_write(UC_ARM64_REG_X21,CONTEXT)
        h.uc.reg_write(UC_ARM64_REG_X0,0)
        h.stops={0x276f60:'normal',0x71b880:'native_logger'}
        h.run(HOOK)
        self.assertEqual(h.outcome,'normal')
        self.assertEqual(struct.unpack('<Q',h.uc.mem_read(0x120a3c88,8))[0],2)

    def test_marker_guard_and_recovery(self):
        for resource,present,close_ok,expected in ((227,True,True,1),(227,False,True,0),
                                                    (227,True,False,0),(226,True,True,1)):
            h=Harness(self.data)
            cfg=CONTEXT+0x1000
            h.uc.mem_write(STATE,b'\x01')
            h.uc.mem_write(cfg+6,struct.pack('<HHH',resource,30,0))
            h.uc.reg_write(UC_ARM64_REG_X19,cfg)
            h.uc.reg_write(UC_ARM64_REG_X0,30)
            logged=[]
            def open_mock(uc):
                if present: uc.mem_write(uc.reg_read(UC_ARM64_REG_X2),struct.pack('<Q',CONTEXT+0x500))
                return 0 if present else 1
            def log_mock(uc): logged.append(uc.reg_read(UC_ARM64_REG_X4)); return 0
            h.mocks={0x26a860:open_mock,0x26a8a0:lambda uc:0 if close_ok else 1,0x71b880:log_mock}
            h.stops={CONFIG_HOOK+4:'native_continuation'}
            h.run(CONFIG_HOOK)
            self.assertEqual(h.outcome,'native_continuation')
            self.assertEqual(bytes(h.uc.mem_read(STATE,1))[0],expected)
            self.assertEqual(logged,[expected] if resource==227 else [])
            self.assertEqual(struct.unpack('<HH',h.uc.mem_read(cfg+8,4)),(30,30))

    def test_disabled_marker_does_not_force_logging(self):
        h=Harness(self.data)
        h.uc.mem_write(CONTEXT+0x16,struct.pack('<H',7680))
        h.uc.reg_write(UC_ARM64_REG_X21,CONTEXT)
        h.uc.reg_write(UC_ARM64_REG_X0,0)
        h.stops={0x276f60:'normal',0x276fa4:'debug'}
        h.run(HOOK)
        self.assertEqual(h.outcome,'normal')

    def test_live_photo_then_8k_preserves_armed_state(self):
        h=Harness(self.data); cfg=CONTEXT+0x1000
        def open_mock(uc):
            uc.mem_write(uc.reg_read(arm.UC_ARM64_REG_X2),struct.pack('<Q',CONTEXT+0x500))
            return 0
        h.mocks={0x26a860:open_mock,0x26a8a0:lambda uc:0,0x71b880:lambda uc:0}
        for resource in (227,1):
            h.uc.mem_write(cfg+6,struct.pack('<HHH',resource,30,0))
            h.uc.reg_write(arm.UC_ARM64_REG_X19,cfg)
            h.uc.reg_write(arm.UC_ARM64_REG_X0,30)
            h.stops={CONFIG_HOOK+4:'native_continuation'}
            h.outcome=None
            h.run(CONFIG_HOOK)
            self.assertEqual(bytes(h.uc.mem_read(STATE,1))[0],1)
        h.uc.mem_write(CONTEXT+0x16,struct.pack('<H',7680))
        h.uc.reg_write(arm.UC_ARM64_REG_X21,CONTEXT)
        h.uc.reg_write(arm.UC_ARM64_REG_X0,0)
        h.stops={0x276f60:'normal',0x276fa4:'debug'}
        h.outcome=None
        h.run(HOOK)
        self.assertEqual(h.outcome,'debug')

    def test_config_hook_preserves_state_across_io(self):
        h=Harness(self.data); cfg=CONTEXT+0x1000
        regs=[getattr(arm,'UC_ARM64_REG_X%d'%i) for i in range(31)]
        vectors=[getattr(arm,'UC_ARM64_REG_Q%d'%i) for i in range(32)]
        for i,r in enumerate(regs): h.uc.reg_write(r,0x12340000+i)
        for i,r in enumerate(vectors): h.uc.reg_write(r,(i+1)*0x123456789abcdef)
        h.uc.mem_write(cfg+6,struct.pack('<HHH',227,30,0))
        h.uc.reg_write(arm.UC_ARM64_REG_X0,30)
        h.uc.reg_write(arm.UC_ARM64_REG_X19,cfg)
        h.uc.reg_write(arm.UC_ARM64_REG_NZCV,0xa0000000)
        old=[h.uc.reg_read(r) for r in regs]
        qold=[h.uc.reg_read(r) for r in vectors]
        sp=h.uc.reg_read(arm.UC_ARM64_REG_SP)
        def clobber(uc):
            for r in regs[1:19]: uc.reg_write(r,0xdeadbeef)
            for r in vectors: uc.reg_write(r,0)
            uc.reg_write(arm.UC_ARM64_REG_NZCV,0)
        def open_mock(uc):
            uc.mem_write(uc.reg_read(arm.UC_ARM64_REG_X2),struct.pack('<Q',CONTEXT+0x500))
            clobber(uc);return 0
        def close_mock(uc): clobber(uc);return 0
        def log_mock(uc): clobber(uc);return 0
        h.mocks={0x26a860:open_mock,0x26a8a0:close_mock,0x71b880:log_mock}
        h.stops={CONFIG_HOOK+4:'native_continuation'}
        h.run(CONFIG_HOOK)
        self.assertEqual([h.uc.reg_read(r) for r in regs],old)
        self.assertEqual([h.uc.reg_read(r) for r in vectors],qold)
        self.assertEqual(h.uc.reg_read(arm.UC_ARM64_REG_NZCV),0xa0000000)
        self.assertEqual(h.uc.reg_read(arm.UC_ARM64_REG_SP),sp)


if __name__=='__main__':
    unittest.main()
