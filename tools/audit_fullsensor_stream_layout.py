"""Compare native Live Photo and full-sensor template recording fields.

This is a static read of the supplied firmware; actual video dimensions,
stream enablement, timing and camera playback are not emulated.
"""
import json
import struct

from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE, read_format
from livephoto_harness import BASE, ROOT, image


def inspect(index):
    data = image()
    start = FORMAT_BASE - 0x20 - BASE + index * FORMAT_STRIDE
    stream_count, stream_mask = struct.unpack_from('<II', data, start + 0xd5c8)
    if stream_count > 4:
        raise ValueError('Unexpected stream count')
    streams = []
    for stream in range(stream_count):
        offset = start + 0xd5d4 + stream * 0x500
        frame_rate = list(struct.unpack_from('<II', data, offset + 0x24))
        width, height = struct.unpack_from('<HH', data, offset + 0x64)
        streams.append(dict(index=stream, canvas=[width, height],
                            frame_rate_words=frame_rate,
                            first_word=hex(struct.unpack_from('<I', data, offset)[0])))
    profile = read_format(data, index)
    return dict(index=index, label=profile['label'], vin_tree=profile['vin_tree'],
                sensor_mode=profile['sensor_mode'], sensor_rate_words=profile['frame_rate_words'],
                stream_count=stream_count, stream_mask=hex(stream_mask), streams=streams)


if __name__ == '__main__':
    result = dict(working_live_4x3=inspect(16), native_full_sensor=inspect(42),
                  limitations=['Template canvas sizes can differ from actual encoded output.',
                               'Stream identifiers, record mask, file generation and playback require further verification.',
                               'Different configured input and output rates do not prove a fault; native rate conversion has not been traced.'],
                  camera_changed=False, firmware_created=False)
    path = ROOT / 'analysis/motion-resolution-audit/fullsensor-stream-layout.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
