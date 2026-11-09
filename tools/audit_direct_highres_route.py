"""Audit native direct profiles and probe a hypothetical direct mode-16 setup.

Static data and isolated callback only; no stream, sensor or image is produced.
"""
import json
import struct
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, read_format, read_modes
from livephoto_harness import BASE, ROOT, image
from probe_fullsensor_actual_callback import probe


def audit():
    d=image(); modes=read_modes(d); profiles=[]
    for i in range(60):
        f=read_format(d,i); mode=modes[f['sensor_mode']]
        if mode['width']<=4096 or f['has_memory_raw_node']:
            continue
        p=FORMAT_BASE-0x20-BASE+i*FORMAT_STRIDE
        profiles.append(dict(format=i,label=f['label'],sensor_mode=f['sensor_mode'],
            sensor_size=[mode['width'],mode['height']],source_rect=mode['source_rect'],
            nominal_sensor_fps=mode['nominal_fps'],vin_tree=f['vin_tree'],
            template_still_raw_size=list(struct.unpack_from('<HH',d,p+0x187f8))))
    overrides={0xc18:struct.pack('<I',16),0x18800:struct.pack('<I',16),
               0x187f8:struct.pack('<HH',8192,6144)}
    cases=[probe(16,30,True,n,overrides) for n in (0,1)]
    return dict(registered_direct_high_width_profiles=profiles,
        experimental_direct_live_callback=cases,
        limitations=['Only three values in a copied direct Live Photo template were changed; other sensor, view, stream and memory geometry remain unmodified and inconsistent.',
          'The callback experiment mocks configuration reads, frame lookup, EIS setup and other camera services. It does not run the sensor, full callback pipeline, DSP, still capture or encoder.',
          'The 4736x3552 narrow mode covers only a central sensor crop, and its static raw descriptor does not prove it can save a full-size Live Photo.',
          'A full-sensor direct profile at 30 fps is not registered among the 60 templates; this does not prove it is impossible.',
          'No firmware created or camera changed.'])


if __name__=='__main__':
    result=audit()
    (ROOT/'analysis/motion-resolution-audit/direct-highres-route.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
