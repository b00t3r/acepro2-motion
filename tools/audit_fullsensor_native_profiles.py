"""Find full-height sensor formats in the firmware's 60 registered templates.

Sensor-table dimensions and static descriptors do not prove which modes work
at runtime, or whether a different still-capture mode can switch sensors.
"""
import json
import struct
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, read_format, read_modes
from livephoto_harness import BASE, ROOT, image


def audit():
    data=image()
    modes=read_modes(data)
    rows=[]
    for i in range(60):
        profile=read_format(data,i)
        mode=profile['sensor_mode']
        if mode >= len(modes): raise ValueError('Unexpected sensor mode')
        if (modes[mode]['width'],modes[mode]['height']) != (8192,6144): continue
        p=FORMAT_BASE-0x20-BASE+i*FORMAT_STRIDE
        capture_id=struct.unpack_from('<H',data,p+0x18cfa)[0]
        count,mask=struct.unpack_from('<II',data,p+0xd5c8)
        fov_count=struct.unpack_from('<I',data,p+0x4418)[0]
        if count>4 or fov_count>8: raise ValueError('Unexpected format geometry')
        fovs=[]
        for n in range(fov_count):
            off=p+0x441c+n*0x104
            fovs.append(dict(index=n,source_kind=struct.unpack_from('<I',data,off+0xa8)[0],
                main_lookup_type=struct.unpack_from('<I',data,off+0xc8)[0],
                sub_lookup_flags=struct.unpack_from('<I',data,off+0xd8)[0],
                iq_word=hex(struct.unpack_from('<I',data,off+0xe8)[0])))
        rows.append(dict(format=i,capture_id=capture_id,sensor_mode=mode,
            sensor_input_rate=profile['configured_fps'], vin_window=profile['vin_window'],
            vin_tree=profile['vin_tree'], recording_stream_count=count,
            recording_stream_mask=hex(mask), fovs=fovs, label=profile['label']))
    return dict(total_formats_inspected=60,full_height_sensor_formats=rows,
        limitations=['Sensor input dimensions are taken from native mode tables; sensor hardware was not run.',
                     'Other formats may switch to a different sensor mode for a still photo.',
                     'Static similarities do not validate stabilization, zoom, video or photo quality.'],
        camera_changed=False)


if __name__=='__main__':
    result=audit()
    output=ROOT/'analysis/trial-h-bootloop/fullsensor-native-profiles.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
