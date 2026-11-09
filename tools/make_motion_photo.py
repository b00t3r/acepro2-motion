"""Package a copied Insta360 JPEG/MP4 pair; never alters camera files.

Uses Android Motion Photo 1.0 Camera/Container XMP. Preserves any
post-EOI vendor data as explicitly declared primary-image padding.
Native Insta360 playback compatibility is not implied.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def jpeg_end(data):
    if data[:2] != b'\xff\xd8':
        raise ValueError('Input is not a JPEG')
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError('Invalid JPEG marker')
        while data[pos] == 255:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            return pos
        if marker == 0 or 0xD0 <= marker <= 0xD7:
            continue
        size = int.from_bytes(data[pos:pos + 2], 'big')
        if size < 2 or pos + size > len(data):
            raise ValueError('Invalid JPEG segment length')
        pos += size
        if marker == 0xDA:
            while pos + 1 < len(data):
                following = data[pos + 1]
                if data[pos] == 255 and following not in (0, 255) and not 0xD0 <= following <= 0xD7:
                    break
                pos += 1
    raise ValueError('JPEG end marker missing')


def package(jpeg, video, timestamp_us=-1, legacy_tags=False):
    end = jpeg_end(jpeg)
    if b'http://ns.adobe.com/xap/1.0/\x00' in jpeg[:end]:
        raise ValueError('Existing XMP requires merging; refusing duplicate XMP')
    if video[4:8] != b'ftyp':
        raise ValueError('Expected an MP4 with an initial ftyp box')
    if timestamp_us < -1:
        raise ValueError('Timestamp must be -1 (unknown) or nonnegative')
    legacy = (f'Camera:MicroVideo="1" Camera:MicroVideoVersion="1" '
              f'Camera:MicroVideoOffset="{len(video)}" '
              f'Camera:MicroVideoPresentationTimestampUs="{timestamp_us}"'
              if legacy_tags else '')
    xmp = f'''<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about=""
 xmlns:Camera="http://ns.google.com/photos/1.0/camera/"
 xmlns:Container="http://ns.google.com/photos/1.0/container/"
 xmlns:Item="http://ns.google.com/photos/1.0/container/item/"
 Camera:MotionPhoto="1" Camera:MotionPhotoVersion="1"
 Camera:MotionPhotoPresentationTimestampUs="{timestamp_us}" {legacy}>
<Container:Directory><rdf:Seq>
<rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="image/jpeg" Item:Semantic="Primary" Item:Length="0" Item:Padding="{len(jpeg)-end}"/></rdf:li>
<rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="video/mp4" Item:Semantic="MotionPhoto" Item:Length="{len(video)}"/></rdf:li>
</rdf:Seq></Container:Directory>
</rdf:Description></rdf:RDF></x:xmpmeta>'''.encode()
    payload = b'http://ns.adobe.com/xap/1.0/\x00' + xmp
    segment = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
    # Keep Exif first: older Android JpegExtractor.sniff checks for Exif\0\0
    # in the first APP1 (optionally after APP0), before it ever reads XMP.
    insert = 2
    while insert + 4 <= end and jpeg[insert:insert + 2] in (b'\xff\xe0', b'\xff\xe1'):
        size = int.from_bytes(jpeg[insert + 2:insert + 4], 'big')
        if size < 2 or insert + 2 + size > end:
            raise ValueError('Invalid leading JPEG segment')
        is_exif = jpeg[insert + 4:insert + 10] == b'Exif\x00\x00'
        insert += 2 + size
        if is_exif:
            break
    return jpeg[:insert] + segment + jpeg[insert:] + video, (insert, len(segment))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jpeg', type=Path)
    parser.add_argument('mp4', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--timestamp-us', type=int, default=-1)
    parser.add_argument('--legacy-tags', action='store_true',
                        help='Also write legacy MicroVideo tags for compatibility testing')
    args = parser.parse_args()
    if not args.output.stem.endswith('MP') or args.output.suffix.lower() not in ('.jpg', '.jpeg'):
        parser.error('Output filename must end in MP.jpg per the Motion Photo naming convention')
    jpeg, video = args.jpeg.read_bytes(), args.mp4.read_bytes()
    combined, (insert, added) = package(jpeg, video, args.timestamp_us, args.legacy_tags)
    assert combined[-len(video):] == video
    assert combined[:insert] + combined[insert + added:-len(video)] == jpeg
    with args.output.open('xb') as stream:
        stream.write(combined)
    print(json.dumps({'output': str(args.output), 'bytes': len(combined),
                      'sha256': hashlib.sha256(combined).hexdigest(),
                      'video_byte_exact': True, 'source_jpeg_recoverable_byte_exact': True,
                      'presentation_timestamp_us': args.timestamp_us}, indent=2))


if __name__ == '__main__':
    main()
