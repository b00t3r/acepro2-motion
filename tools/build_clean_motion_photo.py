"""Build a clean Motion Photo from a copied JPEG and an already resized MP4."""
import argparse
import json
import struct
from pathlib import Path
from make_motion_photo import jpeg_end, package


def boxes(data, start=0, end=None):
    end = len(data) if end is None else end
    pos = start
    while pos < end:
        if pos + 8 > end:
            raise ValueError('Truncated MP4 box')
        size, kind = struct.unpack_from('>I4s', data, pos)
        if size == 1:
            if pos + 16 > end:
                raise ValueError('Truncated extended box')
            size = struct.unpack_from('>Q', data, pos + 8)[0]
        if size == 0:
            size = end - pos
        if size < 8 or pos + size > end:
            raise ValueError('Invalid MP4 box bounds')
        yield pos, size, kind
        pos += size


def clean_video(data):
    top = list(boxes(data))
    if any(t == b'moof' for _, _, t in top):
        raise ValueError('Fragmented video is not supported')
    moovs = [(p, n) for p, n, t in top if t == b'moov']
    if len(moovs) != 1:
        raise ValueError('Expected one moov')
    start, size = moovs[0]
    children = list(boxes(data, start + 8, start + size))
    removed = sum(n for _, n, t in children if t == b'udta')
    if not removed:
        raise ValueError('No user-data box to remove')
    moov = bytearray(struct.pack('>I4s', size - removed, b'moov') + b''.join(
        data[p:p+n] for p, n, t in children if t != b'udta'))

    def fix_offsets(begin, end):
        for p, n, kind in boxes(moov, begin, end):
            if kind in (b'trak', b'mdia', b'minf', b'stbl'):
                fix_offsets(p + 8, p + n)
            elif kind in (b'stco', b'co64'):
                width = 4 if kind == b'stco' else 8
                count = int.from_bytes(moov[p+12:p+16], 'big')
                if 16 + width * count != n:
                    raise ValueError('Invalid chunk offset table')
                for i in range(count):
                    at = p + 16 + i * width
                    old = int.from_bytes(moov[at:at+width], 'big')
                    if start <= old < start + size:
                        raise ValueError('Media chunk unexpectedly inside moov')
                    new = old - removed if old >= start + size else old
                    moov[at:at+width] = new.to_bytes(width, 'big')
    fix_offsets(8, len(moov))
    cleaned = data[:start] + moov + data[start+size:]
    # Encoded media is untouched; only metadata and chunk locations change.
    before = [data[p:p+n] for p, n, t in top if t == b'mdat']
    after = [cleaned[p:p+n] for p, n, t in boxes(cleaned) if t == b'mdat']
    if not before or before != after:
        raise ValueError('Media data changed')
    return bytes(cleaned), removed


def protobuf_fields(data):
    def varint(pos):
        value = 0
        for shift in range(0, 70, 7):
            c = data[pos]
            pos += 1
            value |= (c & 127) << shift
            if c < 128:
                return value, pos
        raise ValueError('Invalid varint')
    pos = 0
    while pos < len(data):
        tag, pos = varint(pos)
        num, wire = tag >> 3, tag & 7
        if not num:
            return
        if wire == 0:
            value, pos = varint(pos)
        elif wire == 2:
            length, pos = varint(pos)
            value = data[pos:pos+length]
            pos += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            value = data[pos:pos+length]
            pos += length
        else:
            return
        if pos > len(data):
            raise ValueError('Truncated protobuf')
        yield num, wire, value


def capture_timestamp_ms(jpeg):
    # Firmware ExtraMetadata field 160 = file_scene_info; nested field 3 is
    # caputre_timestamp (spelling from firmware). Logs corroborate milliseconds.
    model = jpeg.rfind(b'Insta360 Ace Pro 2')
    starts = [p for p in range(max(0, model-100), model-2)
              if jpeg[p] == 10 and p+2+jpeg[p+1] == model-2
              and jpeg[model-2:model] == b'\x12\x12']
    if len(starts) != 1:
        raise ValueError('Could not identify Insta360 metadata')
    for num, wire, value in protobuf_fields(jpeg[starts[0]:]):
        if num == 160 and wire == 2:
            scene = {n: v for n, _, v in protobuf_fields(value)}
            if scene.get(1) != 1 or not isinstance(scene.get(3), int):
                raise ValueError('Not a recognized Live Photo scene')
            return scene[3]
    raise ValueError('Capture timestamp missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jpeg', type=Path)
    parser.add_argument('resized_mp4', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--legacy-tags', action='store_true')
    args = parser.parse_args()
    if not args.output.name.endswith('MP.jpg'):
        parser.error('Output must end with MP.jpg')
    jpeg = args.jpeg.read_bytes()
    timestamp = capture_timestamp_ms(jpeg)
    end = jpeg_end(jpeg)
    video, removed = clean_video(args.resized_mp4.read_bytes())
    result, _ = package(jpeg[:end], video, timestamp * 1000, args.legacy_tags)
    with args.output.open('xb') as stream:
        stream.write(result)
    video_path = args.output.with_suffix('.mp4')
    with video_path.open('xb') as stream:
        stream.write(video)
    report = {'output': str(args.output), 'bytes': len(result),
              'presentation_timestamp_us': timestamp * 1000,
              'legacy_microvideo_tags': args.legacy_tags,
              'timestamp_source': 'Original JPEG ExtraMetadata.file_scene_info.caputre_timestamp',
              'jpeg_vendor_trailer_removed_bytes': len(jpeg)-end,
              'video_metadata_removed_bytes': removed,
              'encoded_video_media_unchanged': True,
              'google_photos_playback': 'not yet verified'}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
