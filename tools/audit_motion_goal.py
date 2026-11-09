"""Collect local evidence for full-resolution still plus ~1080p motion.

The format inventory and old full-resolution photo log are evidence, not an
implementation or proof of concurrent still/video operation.
"""
import json
import re
import struct
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, read_format, read_modes
from livephoto_harness import BASE, ROOT, image


def audit():
    d=image(); modes=read_modes(d); rows=[]
    for i in range(60):
        profile=read_format(d,i); p=FORMAT_BASE-0x20-BASE+i*FORMAT_STRIDE
        count=struct.unpack_from('<I',d,p+0xd5c8)[0]
        if count>4: raise ValueError('Unexpected stream count')
        streams=[]
        for k in range(count):
            off=p+0xd5d4+k*0x500
            w,h=struct.unpack_from('<HH',d,off+0x64)
            scale,tick=struct.unpack_from('<II',d,off+0x24)
            flags=struct.unpack_from('<I',d,off)[0]
            if h==1080 and w>=1440:
                streams.append(dict(index=k,canvas=[w,h],type_flags=hex(flags),
                                    rate=[scale,tick]))
        if streams:
            mode=profile['sensor_mode']
            rows.append(dict(format=i,capture_id=struct.unpack_from('<H',d,p+0x18cfa)[0],
                sensor_mode=mode,sensor_output=[modes[mode]['width'],modes[mode]['height']],
                name=profile['label'],streams=streams))
    log=ROOT/'analysis/motion-resolution-audit/baseline-50mp/logs/decoded/20261030_02.log.txt'
    lines=log.read_text(errors='replace').splitlines()
    needles=('MediaLiveview_StopForStill() begin','MediaLiveview_StopForStill() done',
             'Config Mode: 33','MediaLiveview_StartFromStill() begin','MediaLiveview_StartFromStill() done')
    events=[]
    cursor=0
    for needle in needles:
        for i in range(cursor,len(lines)):
            if needle in lines[i]:
                timestamp=re.match(r'\[(\d+)\]',lines[i])
                if not timestamp: raise ValueError('Expected time marker')
                events.append(dict(line=i+1,ticks=int(timestamp[1]),text=lines[i]));cursor=i+1;break
        else: raise ValueError('Missing still-path event: '+needle)
    return dict(native_1080_high_streams=rows,ordinary_full_resolution_capture=dict(
        source=str(log.relative_to(ROOT)),events=events,
        start_stop_to_preview_return_ticks=events[-1]['ticks']-events[0]['ticks'],
        livephoto_enabled=False),
        limitations=['Static stream canvas is not proof of actual mux output, codec or compatibility with Live Photo.',
                     'Ordinary high-resolution capture did not record a Live Photo; it does not establish whether video can span this sensor switch.',
                     '1920x1080 is 16:9; 1440x1080 preserves 4:3. Their appearance and Google Photos support must be tested.',
                     'No change to camera or firmware.'])


if __name__=='__main__':
    result=audit();out=ROOT/'analysis/motion-resolution-audit/highres-1080-goal.json'
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
