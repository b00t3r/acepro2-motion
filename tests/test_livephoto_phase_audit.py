"""Execute the stock Live Photo barrier and check observed buffer ownership."""
import re
import struct
import sys
import unittest
from pathlib import Path
from unicorn.arm64_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from livephoto_harness import Harness, CONTEXT
from audit_livephoto_phases import phases, LOG


class LivePhotoPhaseAuditTests(unittest.TestCase):
    def test_native_live_route_waits_then_restores_metadata_before_dispatch(self):
        for live in (0,1):
            h=Harness();sp=h.uc.reg_read(UC_ARM64_REG_SP);events=[]
            h.uc.mem_write(sp+0xa4,struct.pack('<I',1))
            h.uc.mem_write(sp+0xb8,struct.pack('<Q',CONTEXT+0x1000))
            h.uc.reg_write(UC_ARM64_REG_X19,CONTEXT)
            h.uc.reg_write(UC_ARM64_REG_X27,CONTEXT+0x1000)
            h.uc.mem_write(CONTEXT+0x1038,struct.pack('<Q',0x71000100))
            def wait(uc):
                self.assertEqual(uc.reg_read(UC_ARM64_REG_X0),0)
                events.append('record_stop_barrier')
            def metadata(uc):
                self.assertEqual((uc.reg_read(UC_ARM64_REG_X0),uc.reg_read(UC_ARM64_REG_X1)),(0,0))
                events.append('metadata_setup')
            h.mocks={0x403820:lambda uc:live,0x3008e0:wait,
                     0x8bcc80:metadata,0x71000100:lambda uc:events.append('dispatch_still')}
            h.stops[0x755940]='dispatched'
            h.run(0x755918)
            self.assertEqual(events,['record_stop_barrier','metadata_setup','dispatch_still'] if live else ['dispatch_still'])

    def test_native_barrier_uses_one_nonclearing_event_and_60_second_timeout(self):
        h=Harness();h.uc.mem_map(0x12216000,0x50000)
        observed=[]
        def event_get(uc):
            observed.append([uc.reg_read(r) for r in (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X4)])
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X3),struct.pack('<I',1))
            return 0
        h.mocks={0x1787c60:event_get,0x2639a0:lambda uc:0,0x71b880:lambda uc:0}
        h.uc.reg_write(UC_ARM64_REG_X0,0)
        h.run(0x3008e0)
        # ThreadX option 2: AND without CLEAR. A later wait can see the same
        # completion bit; this alone does not prove moving it is safe.
        self.assertEqual(observed,[[0x12257c68,1,2,60000]])

    def test_hardware_pureshot_already_overlaps_and_video_jpeg_buffers_overlap(self):
        rows=phases();self.assertEqual(len(rows),4)
        self.assertTrue(all(r['pureshot_already_overlaps_video'] for r in rows))
        text=LOG.read_text()
        video={int(x,16) for x in re.findall(r'Video\[\d\] Enc Para.*?BufferAddr ([0-9A-Fa-f]+)',text)}
        jpeg={int(x,16) for x in re.findall(r'SvcStillEnc_TaskEntry.*?EncCtrl.BitsBufAddr ([0-9A-Fa-f]+)',text)}
        self.assertEqual(video & jpeg,{0xd0525380})
        self.assertTrue(all(0<r['raw_to_main_yuv_ms']<100 for r in rows))


if __name__=='__main__':unittest.main()
