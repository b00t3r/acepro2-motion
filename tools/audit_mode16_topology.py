"""Compare native streaming topology for the unregistered full-sensor mode.

This reads pinned firmware tables only. No candidate profile, encoder,
sensor-register sequence, image processing or camera execution is performed.
"""
import json
import struct
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, read_format, read_modes
from audit_fullsensor_stream_layout import inspect
from livephoto_harness import BASE, ROOT, image


def audit():
    d=image();modes=read_modes(d);profiles=[]
    for i in (16,26,31,42):
        f=read_format(d,i);p=FORMAT_BASE-0x20-BASE+i*FORMAT_STRIDE
        count=struct.unpack_from('<I',d,p+0x4418)[0]
        if count>8: raise ValueError('Unexpected FOV count')
        fovs=[]
        for n in range(count):
            q=p+0x441c+n*0x104
            fovs.append(dict(index=n,source_kind=struct.unpack_from('<I',d,q+0xa8)[0],
                main_lookup_type=struct.unpack_from('<I',d,q+0xc8)[0],
                sub_lookup_flags=struct.unpack_from('<I',d,q+0xd8)[0]))
        profiles.append(dict(format=i,capture_id=struct.unpack_from('<H',d,p+0x18cfa)[0],
            label=f['label'],sensor_mode=f['sensor_mode'],sensor_fps=f['configured_fps'],
            vin_tree=f['vin_tree'],fovs=fovs,streams=inspect(i)['streams']))
    users=[]
    for i in range(60):
        f=read_format(d,i)
        if f['sensor_mode']==16: users.append(i)
    return dict(sensor_modes=[modes[n] for n in (3,16,33,36,53)],
        registered_profiles_using_mode16=users,profiles=profiles,
        findings=['Format 31 is a native 30 fps profile with both a direct view and a memory-raw feed, but its sensor mode outputs 4096x3072.',
                  'No registered streaming profile among the 60 inspected uses mode 16.',
                  'A full-width 30 fps version of format 31 is a new configuration, not a native supported profile.',
                  'Sensor mode 16 Bayer code 0 differs from the ordinary full-resolution still mode 33 Bayer code 2; their actual photo quality is unknown.'],
        limits=['Static firmware data only; no sensor or DSP processing is executed.',
                'The 30 fps figure is nominal, and the full-resolution readout and concurrent recording have not been measured.',
                'A 1080p stream, buffer sizes, view geometry, ISP tuning, Bayer interpretation and thermal behavior remain unvalidated.'],
        camera_changed=False,firmware_candidate_created=False)


if __name__=='__main__':
    result=audit();out=ROOT/'analysis/motion-resolution-audit/mode16-topology.json'
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'registered_profiles_using_mode16':result['registered_profiles_using_mode16'],
                      'findings':result['findings'],'limits':result['limits']},indent=2))
