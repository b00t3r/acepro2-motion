"""Probe native raw-feed counter-difference branch, without task execution."""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X2, UC_ARM64_REG_X6
from livephoto_harness import BASE, Harness, ROOT, image
from probe_rawfeed_buffer_sizing import GLOBAL


def probe(flag, difference):
    h=Harness()
    h.uc.mem_map(0x141e9000,0xc6000)
    base=GLOBAL+0x80000
    h.uc.reg_write(UC_ARM64_REG_X6,base)
    h.uc.reg_write(UC_ARM64_REG_X2,flag)
    h.uc.reg_write(UC_ARM64_REG_X0,100)
    h.uc.mem_write(base+0x16f4,struct.pack('<I',100-difference))
    h.stops={0x154ca24:'difference_exceeded',0x154c6e8:'within_threshold'}
    h.run(0x154c6c8)
    return dict(flag=flag,difference=difference,outcome=h.outcome,fragment_only=True)


def audit():
    message=b'[Abandon CvRaw!!!]Cause PostRaw (W:%u---R:%u)'
    offset=0x248f578-BASE
    if image()[offset:offset+len(message)] != message:
        raise ValueError('Expected firmware diagnostic message missing')
    return dict(cases=[probe(flag,n) for flag in (0,1) for n in (3,4,30,31)],
        evidence={'task_log_string':'LiveviewTask_CvRawHdlrTask Enter!',
                  'threshold_exceeded_log_string':message.decode(),
                  'threshold_exceeded_effect':'increments a separate raw-feed counter before emitting the message',
                  'camera_log':'analysis/trial-h-bootloop/logs/decoded/20261030_08.log.txt',
                  'camera_log_note':'shows raw processing tasks started in the failed test; it does not show this threshold being exceeded'},
        limitations=['Counter roles, scheduling and the downstream response were not validated.',
                     'Native branch ran with controlled counter values and flag, not live camera data.',
                     'This threshold is separate from buffer address modulo and must be accounted for in a complete design.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-backlog.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
