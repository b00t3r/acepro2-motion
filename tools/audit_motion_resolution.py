"""Read the pinned sensor and capture tables; never change camera or firmware.

Field locations follow OV50H40's native table initialiser at 0x14b8680,
GetModeInfo at 0x14b5300, and photo lookup at 0x3611c0. A configuration
present in this image is not proof that it works in Live Photo mode.
"""
import json
import struct
from pathlib import Path

from livephoto_harness import BASE, EXPECTED_IMAGE_SHA, image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_INFO = 0x1e7c918
INPUT_INFO = 0x1e7c0e0
TIMING_INFO = 0x3cfdae0
MODE_COUNT = 75  # Native GetModeInfo checks index <= 0x4a.
FORMAT_BASE = 0x1e94cf0
FORMAT_STRIDE = 0x18e38


def read_modes(data):
    rows = []
    for index in range(MODE_COUNT):
        out = OUTPUT_INFO - BASE + 32 * index
        inp = INPUT_INFO - BASE + 28 * index
        width, height = struct.unpack_from('<HH', data, out + 12)
        x, y, source_w, source_h = struct.unpack_from('<4H', data, inp)
        timing = struct.unpack_from('<9I', data, TIMING_INFO - BASE + 36 * index)
        rows.append(dict(
            mode=index, width=width, height=height,
            raw_megapixels=round(width * height / 1e6, 4),
            output_bits=data[out + 9], bayer_code=data[out + 10],
            source_rect=[x, y, source_w, source_h],
            horizontal_extent_fraction=source_w / 8192,
            input_descriptor_hex=data[inp:inp + 28].hex(),
            timing_words=list(timing),
            nominal_fps=timing[5] / timing[6] if timing[6] else None,
            hdr_type=timing[7],
        ))
    return rows


def read_format(data, index):
    start = FORMAT_BASE - BASE + index * FORMAT_STRIDE
    label = data[start:start + 128].split(b'\0')[0].decode('ascii')
    tree = data[start + 128:start + 0x480].split(b'\0')[0].decode('ascii')
    mode = struct.unpack_from('<I', data, start + 0xbf8)[0]
    width, height = struct.unpack_from('<HH', data, start + 0x4a0)
    scale, tick = struct.unpack_from('<II', data, start + 0x504)
    return dict(format_index=index, address=hex(start + BASE), label=label,
                vin_tree=tree, sensor_mode=mode, vin_window=[width, height],
                frame_rate_words=[scale, tick],
                configured_fps=scale / tick if tick else None,
                has_memory_raw_node='[M_RAW_' in tree)


def audit(data):
    modes = read_modes(data)
    # Include regular 8K, both ordinary still aspect ratios, current Live Photo,
    # native MRAW, narrow video, and the misleadingly named 8K MRAW formats.
    formats = [read_format(data, i) for i in (7, 8, 12, 13, 15, 31, 32, 33, 34, 36, 42, 43)]
    photos = [list(struct.unpack_from('<7I', data, 0x25e4ae0 - BASE + i * 28))
              for i in range(11)]
    return dict(
        source_sha256=EXPECTED_IMAGE_SHA, hardware_executed=False,
        sensor_modes=modes, selected_formats=formats,
        photo_descriptors=photos,
        photo_descriptor_fields=['resolution_id', 'nominal_width', 'nominal_height',
                                 'resource_a', 'resource_b', 'capture_id', 'actual_mode'],
        findings={
            'live_photo': 'Mode 36: 4096x3072 raw, 14-bit output, HDR type 2; 16:9 JPEG is 4096x2304.',
            'intermediate': 'Modes 21-26: 4736x3552, but source is a 4736x3552 centre crop of the 8192x6144 array. Not a wider, higher-detail replacement at the same field of view.',
            'high_resolution_mraw': 'Formats 42/43 have M_RAW nodes and 8192x6144 input, but configure mode 53 at 5 fps, despite P30 labels. Not a ready-made smooth-motion replacement.',
            'regular_8k': 'Format 7 uses mode 20: 8192x4608 sensor output at 24 fps. Its VIN tree has no M_RAW node. A simultaneous still raw tap is not established.',
            'photo_lookup': 'Only resolution IDs 2/3/6 have actual_mode 17 entries. No native intermediate Live Photo descriptor exists in this lookup.',
            'next_requirement': 'Establish a full-resolution raw capture path alongside the regular video/HDS pipeline, including buffer sizing, Bayer/remosaic handling and matching ISP tuning, before building a candidate.',
        },
        limits=['Static tables only; no sensor, DSP, image-quality or concurrent-capture validation.',
                'Nominal sensor timing is not a measured frame rate.',
                'No firmware candidate created or staged.'],
    )


if __name__ == '__main__':
    report = audit(image())
    folder = ROOT / 'analysis/motion-resolution-audit'
    folder.mkdir(exist_ok=True)
    (folder / 'sensor-and-resource-tables.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['findings'], indent=2))
