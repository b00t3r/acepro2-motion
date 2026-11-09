"""Compare native still-raw settings against recorded 4K and 8K logs.

Static inspection and real recorded log evidence only. No camera modification.
"""
import json
import struct
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE
from livephoto_harness import BASE,ROOT,image


def template(index):
    d=image(); p=FORMAT_BASE-0x20-BASE+index*FORMAT_STRIDE
    return dict(index=index,still_raw_enabled=d[p+0x187ec],
        bytes_at_187ec=d[p+0x187ec:p+0x187f8].hex(),
        raw_size=list(struct.unpack_from('<HH',d,p+0x187f8)))


def evidence(path, needles, start=1, end=None):
    lines=(ROOT/path).read_text(errors='replace').splitlines()
    out=[]
    for needle in needles:
        found=[(i+1,line) for i,line in enumerate(lines)
               if start <= i+1 <= (end or len(lines)) and needle in line]
        if not found: raise ValueError('Missing log evidence: '+needle)
        i,line=found[-1]
        out.append(dict(line=i,text=line))
    return dict(path=path,events=out)


def audit():
    return dict(templates=[template(i) for i in (7,15,16)],
        observed_8k=evidence('analysis/direct-8k-hardware/logs/decoded/20261030_01.log.txt',
          ['Config Mode: 20','enable still raw 0','7680x4320,24fps[24000/1000]','1280x720,24fps[24000/1000]'],2781,3770),
        observed_4k=evidence('analysis/video-snapshot-baseline/logs/decoded/20261030_16.log.txt',
          ['Config Mode: 38','enable still raw 1','Rawpiv raw in video','Recv RawBuff:0x805a1480'],7666,9000),
        firmware_reference='Native code at 0x15293ac reads the still-raw flag and branches into additional pitch/setup logic when enabled.',
        limitations=['Templates and logs agree on the flag, but they do not prove the template byte is never changed by runtime setup.',
          '8K sensor raw compression, still buffer pitch, allocation and processing compatibility remain unresolved.',
          'Logged pool sizes are from specific moments and do not establish free memory during a hypothetical 8K still.',
          'No firmware, camera or card changes.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/still-raw-switch.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
