"""Inspect native 8K direct profile and execute its configuration callback.

Profile and callback outputs are not evidence of a simultaneous still capture.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from audit_motion_resolution import FORMAT_BASE,FORMAT_STRIDE
from audit_fullsensor_stream_layout import inspect
from livephoto_harness import BASE,CONTEXT,Harness,ROOT,image
from probe_capture_template_callback import probe as descriptor


def experiment(raw_size=None):
    h=Harness((ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    p=FORMAT_BASE-0x20-BASE+7*FORMAT_STRIDE
    h.uc.mem_write(CONTEXT,image()[p:p+FORMAT_STRIDE])
    if raw_size is not None:
        h.uc.mem_write(CONTEXT+0x187f8,struct.pack('<HH',*raw_size))
    queries=[]
    def config(uc):
        key,size=uc.reg_read(UC_ARM64_REG_X0),uc.reg_read(UC_ARM64_REG_X2)
        if (key,size)==(0x1c,8): data=struct.pack('<IBHB',1,0,100,0)
        elif (key,size)==(0x2d,4): data=bytes(4)
        else: raise ValueError('Unexpected configuration query %x/%s'%(key,size))
        queries.append([key,size]);uc.mem_write(uc.reg_read(UC_ARM64_REG_X1),data);return 0
    h.mocks={0x263900:lambda uc:0,0x17d5cc0:lambda uc:0,0x2639a0:lambda uc:0,
        0x71b880:lambda uc:0,0x7745e0:lambda uc:1,0x294a20:lambda uc:0,
        0x28a520:lambda uc:0,0x2e7040:lambda uc:0,0x1786ac0:lambda uc:0,
        0x28ff60:lambda uc:0,0x2e41a0:config,0x2e4380:config}
    h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X1,int(descriptor(10)['descriptor'],16))
    h.run(0x294f60,100000)
    raw=list(struct.unpack('<HH',h.uc.mem_read(CONTEXT+0x187f8,4)))
    mode=struct.unpack('<I',h.uc.mem_read(CONTEXT+0xc18,4))[0]
    return dict(initial_raw_size=raw_size or [0,0],final_raw_size=raw,sensor_mode=mode,
                status=h.uc.reg_read(UC_ARM64_REG_X0),queries=queries,
                mocks=[hex(a) for a in sorted(h.mocks)],hardware_executed=False)


def audit():
    return dict(static_profile=inspect(7), callback=descriptor(10),
        experiments=[experiment(),experiment([8192,4608])],
        limitations=['Raw size override is an in-memory counterfactual, not a valid or safe camera configuration.',
                     'Many services including EIS and configuration reads are mocked. No sensor, still, video, allocation or codec is executed.',
                     'The native 8K profile has one direct view and 24 fps streams. Its main video stream is not a full-quality still.',
                     'Video profile is 16:9; 4:3 full-height capture would need different configuration.',
                     'No firmware created or camera changed.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/direct-8k-photo.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
