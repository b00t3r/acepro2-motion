"""Validate an on-device Motion Photo against its two source files.

This is a host-side audit, not a camera-side implementation or durability test.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

XMP = b'http://ns.adobe.com/xap/1.0/\0'
ITEM = '{http://ns.google.com/photos/1.0/container/item/}'
CAMERA = '{http://ns.google.com/photos/1.0/camera/}'


def check(jpeg, lrv, motion):
    if not (jpeg.startswith(b'\xff\xd8\xff\xe1') and motion.startswith(b'\xff\xd8\xff\xe1')):
        raise ValueError('Expected a JPEG starting with EXIF APP1')
    end_exif = 4 + int.from_bytes(jpeg[4:6], 'big')
    if motion[:end_exif] != jpeg[:end_exif] or motion[end_exif:end_exif+2] != b'\xff\xe1':
        raise ValueError('Original EXIF or inserted APP1 mismatch')
    length = int.from_bytes(motion[end_exif+2:end_exif+4], 'big')
    after_xmp = end_exif + 2 + length
    payload = motion[end_exif+4:after_xmp]
    if not payload.startswith(XMP):
        raise ValueError('Missing XMP header')
    root = ET.fromstring(payload[len(XMP):])
    elements = list(root.iter())
    desc = [e for e in elements if CAMERA+'MotionPhoto' in e.attrib]
    video = [e for e in elements if e.attrib.get(ITEM+'Semantic') == 'MotionPhoto']
    if len(desc) != 1 or desc[0].attrib[CAMERA+'MotionPhoto'] != '1' or len(video) != 1:
        raise ValueError('Invalid motion metadata')
    if int(video[0].attrib[ITEM+'Length']) != len(lrv):
        raise ValueError('Video length metadata mismatch')
    if len(motion) != len(jpeg) + (after_xmp-end_exif) + len(lrv):
        raise ValueError('Unexpected combined size')
    if motion[after_xmp:after_xmp+len(jpeg)-end_exif] != jpeg[end_exif:]:
        raise ValueError('Original JPEG body changed')
    if motion[-len(lrv):] != lrv:
        raise ValueError('Embedded LRV bytes differ')
    return {'original_jpeg_bytes':len(jpeg), 'embedded_video_bytes':len(lrv),
        'motion_bytes':len(motion), 'original_jpeg_preserved':True,
        'video_exact_match':True, 'presentation_timestamp_us':int(desc[0].attrib[CAMERA+'MotionPhotoPresentationTimestampUs'])}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('jpeg',type=Path);p.add_argument('lrv',type=Path);p.add_argument('motion',type=Path)
    a=p.parse_args()
    print(json.dumps(check(a.jpeg.read_bytes(),a.lrv.read_bytes(),a.motion.read_bytes()),indent=2))
