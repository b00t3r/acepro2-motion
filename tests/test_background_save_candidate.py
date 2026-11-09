"""Execute Trial W's packaged worker and actual storage-hook instructions.

Filesystem and scheduler are explicit mocks; these tests do not model RTOS
preemption, the SD controller, native gallery implementation or ISP pixels.
"""
import functools
import json
import struct
import unittest
import lz4.frame
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import *
from test_background_worker_prototype import WorkerMachine, WORK
from build_background_candidate import OUT, SOURCE, SOURCE_SHA, DEST, HOOKS, hook_branch
from build_motion_candidate import BASE, sha
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from build_clean_motion_photo import capture_timestamp_ms
from audit_zoom_isp_selection import replay
from livephoto_harness import run_still_geometry_fragment, run_livephoto_config


@functools.lru_cache(None)
def images():
    return tuple(lz4.frame.decompress(unpack_package(p.read_bytes())['parts'][0]['payload']) for p in (SOURCE,DEST))


def machine(**kwargs):
    report=json.loads((OUT/'build_report.json').read_text())
    return WorkerMachine(image_data=images()[1],symbols=report['symbols'],**kwargs)


def stop_at(m,address):
    return m.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:uc.emu_stop(),begin=address,end=address)


class BackgroundSaveCandidateTests(unittest.TestCase):
    def test_changes_only_worker_regions_storage_guards_and_usb_marker(self):
        old,new=images();report=json.loads((OUT/'build_report.json').read_text())
        self.assertEqual(sha(SOURCE.read_bytes()),SOURCE_SHA)
        wanted=bytearray(old)
        for r in report['regions']:
            a,b=int(r['start'],16)-BASE,int(r['end'],16)-BASE
            wanted[a:b]=new[a:b]
        for a,expected,name,link in HOOKS:
            self.assertEqual(old[a-BASE:a-BASE+4],bytes.fromhex(expected))
            wanted[a-BASE:a-BASE+4]=hook_branch(a,report['symbols'][name],link)
        for at in USB_OFFSETS:wanted[at:at+18]=b'Insta360 Ace Pro W'
        self.assertEqual(new,wanted)
        self.assertEqual(unpack_package(SOURCE.read_bytes())['parts'][1:],unpack_package(DEST.read_bytes())['parts'][1:])
        self.assertEqual(old[0x50e80-BASE:0x51000-BASE],new[0x50e80-BASE:0x51000-BASE])

    def test_producer_returns_without_writing_then_worker_saves_original_data(self):
        m=machine();self.assertIsNone(m.run());self.assertEqual(m.write_count,0)
        self.assertEqual(m.call('motion_worker_capture_busy',0),1)
        self.assertEqual(m.step(),0)
        self.assertEqual(m.call('motion_worker_capture_busy',0),0)
        self.assertEqual(m.files[m.path],m.jpeg)
        self.assertTrue(m.files[m.path[:-4]+'.MP.jpg'].endswith(m.lrv))
        self.assertFalse(m.allocated or m.handles)

    def test_actual_u_captures_produce_byte_identical_motion_photos(self):
        folder=SOURCE.parents[2]/'analysis/trial-u-speed-baseline/captures'
        for p in sorted(folder.glob('*.jpg')):
            if p.name.endswith('.MP.jpg'):continue
            m=machine(jpeg=p.read_bytes(),lrv=p.with_suffix('.lrv').read_bytes(),timestamp=capture_timestamp_ms(p.read_bytes()))
            m.run();self.assertEqual(m.write_count,0);self.assertEqual(m.step(),0)
            self.assertEqual(m.files[m.path[:-4]+'.MP.jpg'],p.with_name(p.stem+'.MP.jpg').read_bytes())

    def test_native_gallery_usb_format_delete_and_poweroff_wait_then_preserve_state(self):
        cases=[(0x879f20,0x879f24,0x170,2), (0x38d1e0,0x38d1e4,0xa0,2),
               (0x7fc080,0x7fc084,0xa0,2), (0x26ab00,0x26ab04,0,0x50000000),
               (0x3a1670,0x3a0e20,0,2)]
        for entry,target,frame,arg in cases:
            with self.subTest(entry=hex(entry)):
                m=machine();m.run();stop_at(m,target)
                m.uc.reg_write(UC_ARM64_REG_SP,0x70018000)
                m.uc.reg_write(UC_ARM64_REG_X30,0x71000000)
                m.uc.reg_write(UC_ARM64_REG_X0,arg)
                m.uc.reg_write(UC_ARM64_REG_NZCV,0xa0000000)
                regs=[UC_ARM64_REG_X0+i for i in range(19)]
                before=[m.uc.reg_read(r) for r in regs]
                m.uc.emu_start(entry,0x71000000,count=100000)
                self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),0x25ef40)
                sleeping=m.uc.context_save()
                self.assertEqual(m.step(),0)
                m.uc.context_restore(sleeping)
                m.uc.reg_write(UC_ARM64_REG_PC,m.uc.reg_read(UC_ARM64_REG_X30))
                m.uc.emu_start(m.uc.reg_read(UC_ARM64_REG_PC),0x71000000,count=100000)
                self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),target)
                self.assertEqual([m.uc.reg_read(r) for r in regs],before)
                self.assertEqual(m.uc.reg_read(UC_ARM64_REG_SP),0x70018000-frame)
                self.assertEqual(m.uc.reg_read(UC_ARM64_REG_NZCV),0xa0000000)

    def test_log_deletion_and_null_delete_do_not_wait_on_worker(self):
        for name,arg,target in [(b'C:\\LOG\\old.log\0',0x50000400,0x26ab04),(b'',0,0x26ab18)]:
            m=machine();m.run();m.uc.mem_write(0x50000400,name);stop_at(m,target)
            m.uc.reg_write(UC_ARM64_REG_SP,0x70018000);m.uc.reg_write(UC_ARM64_REG_X0,arg)
            m.uc.reg_write(UC_ARM64_REG_X30,0x71000000)
            m.uc.emu_start(0x26ab00,0x71000000,count=100000)
            self.assertEqual(m.uc.reg_read(UC_ARM64_REG_PC),target)

    def test_all_shutdown_busy_sites_include_pending_job_without_global_capture_patch(self):
        for at in (0x3a134c,0x3a1440,0x3a14e0):
            m=machine();m.uc.mem_map(0x1243f000,0x1000);m.run();stop_at(m,at+4)
            for native_busy in (0,2):
                m.uc.mem_write(0x1243f134,struct.pack('<I',native_busy))
                m.uc.reg_write(UC_ARM64_REG_SP,0x70018000)
                m.uc.emu_start(at,0x71000000,count=100000)
                self.assertEqual(m.uc.reg_read(UC_ARM64_REG_X0),native_busy or 1)
            self.assertEqual(m.step(),0)
            m.uc.mem_write(0x1243f134,bytes(4));m.uc.reg_write(UC_ARM64_REG_SP,0x70018000)
            m.uc.emu_start(at,0x71000000,count=100000)
            self.assertEqual(m.uc.reg_read(UC_ARM64_REG_X0),0)
        old,new=images()
        self.assertEqual(old[0x32da80-BASE:0x32da8c-BASE],new[0x32da80-BASE:0x32da8c-BASE])

    def test_snapshot_queue_and_failure_fallback_preserve_files(self):
        m=machine(timestamp=1434);m.run()
        m.uc.mem_write(0x1264f320,struct.pack('<Q',9999))
        m.uc.mem_write(0x1262e904,bytes(4))
        m.uc.mem_write(0x50000000,b'C:\\DCIM\\Camera01\\LIV_reused.jpg\0')
        self.assertEqual(m.step(),0)
        self.assertIn(b'PresentationTimestampUs="1434000"',m.files[m.path[:-4]+'.MP.jpg'])
        for kw in ({'task_fail':True},{'resume_fail':True},{'fail':'workspace_alloc'}):
            n=machine(**kw);self.assertIsNotNone(n.run())
            self.assertEqual(n.files[n.path],n.jpeg)

    def test_two_capture_queue_preserves_both_names_and_timestamps(self):
        m=machine(timestamp=1200);m.run()
        second='C:\\DCIM\\Camera01\\LIV_second.jpg'
        m.files[second]=m.jpeg;m.files[second[:-4]+'.lrv']=m.lrv
        m.uc.mem_write(0x50000400,second.encode()+b'\0')
        m.uc.mem_write(0x1264f320,struct.pack('<Q',1600))
        self.assertEqual(m.call('motion_submit',0x50000400,0),0)
        self.assertEqual(m.write_count,0)
        self.assertEqual(m.step(),0)
        self.assertIn(b'PresentationTimestampUs="1200000"',m.files[m.path[:-4]+'.MP.jpg'])
        self.assertEqual(m.call('motion_worker_capture_busy',0),1)
        self.assertEqual(m.step(),0)
        self.assertIn(b'PresentationTimestampUs="1600000"',m.files[second[:-4]+'.MP.jpg'])
        self.assertEqual(m.call('motion_worker_capture_busy',0),0)
        self.assertEqual(m.files[second],m.jpeg)

    def test_failed_background_write_releases_busy_state_without_publishing_partial_file(self):
        m=machine(fail='write');m.run();self.assertEqual(m.step(),0)
        self.assertEqual(m.call('motion_worker_capture_busy',0),0)
        self.assertNotIn(m.path[:-4]+'.MP.jpg',m.files)
        self.assertEqual(m.files[m.path],m.jpeg)
        self.assertFalse(m.allocated or m.handles)

    def test_u_colour_selection_zoom_geometry_and_video_settings_preserved(self):
        old,new=images()
        for raw in (0,1):
            for rec in (0,1):
                a,b=(replay(rec,1,image_data=im,still_type=raw,live_flag=1) for im in (old,new))
                self.assertEqual(a,b);self.assertIn('livephoto',b['table'])
        for live in (False,True):
            self.assertEqual(run_still_geometry_fragment(live,image_data=old),run_still_geometry_fragment(live,image_data=new))
        for narrow in (0,1):
            self.assertEqual(run_livephoto_config(226,narrow=narrow,image_data=old),run_livephoto_config(226,narrow=narrow,image_data=new))


if __name__=='__main__':unittest.main()
