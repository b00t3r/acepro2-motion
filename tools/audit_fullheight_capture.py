"""Native buffer and format decisions for higher-resolution Live Photos.

Software-only: executes pitch arithmetic, format decisions and ISP lookup.
Does not emulate sensor, ISP pixels, neural models, DSP or camera memory.
"""
import json
import re
import struct
from pathlib import Path

from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4,
    UC_ARM64_REG_X5, UC_ARM64_REG_X6)
from livephoto_harness import Harness, CONTEXT, ROOT, image
from audit_capture_pipeline import pureshot_format
from audit_zoom_isp_selection import replay
from audit_motion_resolution import read_modes

WORKING = ROOT / 'builds/offline-background-save/main_threadx.bin'


def native_pitch(width):
    """Run uncompressed pitch arithmetic through the original native code."""
    if not 0 < width <= 8192:
        raise ValueError('Only established sensor widths are supported')
    h = Harness()
    for reg, value in ((UC_ARM64_REG_X0, width), (UC_ARM64_REG_X1, 0),
                       (UC_ARM64_REG_X2, 0), (UC_ARM64_REG_X3, CONTEXT),
                       (UC_ARM64_REG_X4, CONTEXT + 2),
                       (UC_ARM64_REG_X5, CONTEXT + 4),
                       (UC_ARM64_REG_X6, CONTEXT + 6)):
        h.uc.reg_write(reg, value)
    h.run(0xff8880)
    if h.uc.reg_read(UC_ARM64_REG_X0):
        raise RuntimeError('Native pitch query failed')
    return struct.unpack('<HHHH', h.uc.mem_read(CONTEXT, 8))


def plane_sizes(width, height):
    # The native allocator at 0x2813e8 queries raw and quarter-width CE
    # pitches separately, adds them, then multiplies by raw height.
    raw_pitch = native_pitch(width)[1]
    ce_pitch = native_pitch(width // 4)[1]
    return dict(width=width, height=height, raw_pitch=raw_pitch, ce_pitch=ce_pitch,
                raw_bytes=raw_pitch * height, ce_bytes=ce_pitch * height,
                raw_plus_ce_bytes=(raw_pitch + ce_pitch) * height,
                full_size_yuv420_bytes=width * height * 3 // 2)


def logged_evidence():
    paths = [ROOT / 'analysis/trial-w-hardware/logs/decoded/20261029_48.log.txt',
             ROOT / 'analysis/full-resolution-baseline/decoded/20261029_15.log.txt']
    needles = ('StillRawCapBufSize', '[R2yForMain] Raw Pitch',
               '[R2yForMain]  Ce Pitch', 'main yuv done,',
               'MediaLiveview_StopForStill() done', 'Config Mode: 33',
               '[Pure Shot ALG] Success Create')
    evidence = []
    for path in paths:
        lines = path.read_text(errors='replace').splitlines()
        # Save the first occurrence of each distinct message, keeping line
        # numbers and values while avoiding four copies of the same capture.
        seen = set()
        for number, line in enumerate(lines, 1):
            for needle in needles:
                if needle not in line:
                    continue
                value = re.sub(r'^\[\d+\]', '', line)
                if value not in seen:
                    seen.add(value)
                    evidence.append(dict(path=str(path.relative_to(ROOT)), line=number, text=line))
                break
    return evidence


def logged_memory_overlap():
    live_path = ROOT / 'analysis/trial-w-hardware/logs/decoded/20261029_48.log.txt'
    full_path = ROOT / 'analysis/full-resolution-baseline/decoded/20261029_15.log.txt'
    live, full = (p.read_text(errors='replace') for p in (live_path, full_path))
    video = re.search(r'Video\[0\] Enc Para W:3840 H:2160[^\n]*BufferAddr ([0-9A-Fa-f]+) BufferSize (\d+)', live)
    if not video:
        raise ValueError('Expected video-buffer baseline is absent')
    video_base, video_size = int(video[1], 16), int(video[2])
    result = dict(video=dict(base=video_base, size=video_size,
                            end_exclusive=video_base + video_size), layouts=[])
    for text, width, height, label in ((live, 4096, 3072, 'working_live'),
                                        (full, 8192, 6144, 'ordinary_full_resolution')):
        match = re.search(r'\[R2yForMain\] Raw Pitch \d+ Width %d Height %d[^\n]*BaseAddr ([0-9A-Fa-f]+)' % (width, height), text)
        if not match:
            raise ValueError('Expected raw geometry is absent: ' + label)
        base = int(match[1], 16)
        size = plane_sizes(width, height)['raw_plus_ce_bytes']
        overlap = max(0, min(base + size, video_base + video_size) - max(base, video_base))
        pools = list(re.finditer(r'StillBufTotalBase 0x([0-9a-fA-F]+), StillBufTotalSize 0x([0-9a-fA-F]+)', text[:match.start()]))
        if not pools:
            raise ValueError('Still-pool allocation is missing before ' + label)
        pool_base, pool_size = (int(pools[-1][i], 16) for i in (1, 2))
        result['layouts'].append(dict(label=label, base=base, size=size,
                                     end_exclusive=base + size,
                                     overlap_with_video_bytes=overlap,
                                     still_pool_base=pool_base,
                                     still_pool_bytes=pool_size))
    full_minimum = plane_sizes(8192, 6144)
    minimum_bytes = full_minimum['raw_plus_ce_bytes'] + full_minimum['full_size_yuv420_bytes']
    result['existing_full_still_path_minimum_bytes'] = minimum_bytes
    result['shortfall_against_recorded_live_pool_bytes'] = max(0,
        minimum_bytes - result['layouts'][0]['still_pool_bytes'])
    result['minimum_excludes'] = 'PureShot scratch/model memory, extra frame copies, resize buffers, screen/thumbnail, metadata and allocator alignment.'
    result['interpretation'] = 'Layouts were recorded in different modes. Overlap prevents blindly reusing the ordinary-photo allocation concurrently with the existing video reservation; it does not establish current memory corruption or total free RAM.'
    return result


def audit():
    working = WORKING.read_bytes()
    source = image()
    modes = read_modes(source)
    geometry = [plane_sizes(4096, 3072), plane_sizes(8192, 6144)]
    formats = [dict(raw_width=w, decision=pureshot_format(
        narrow=0, raw_width=w, image_data=working, livephoto=True))
        for w in (4096, 8192)]
    tuning = []
    for submode in (12, 17):
        for resolution in (2, 4, 5):
            for still_type in (0, 1):
                tuning.append(replay(recording=0, narrow=0, face=0,
                    image_data=working, still_type=still_type,
                    live_flag=int(submode == 17), sub_mode=submode,
                    resolution=resolution, hdr=1,
                    allow_unmatched=True, lens=0 if submode == 12 else 1))
    return dict(
        hardware_executed=False, firmware_created=False,
        sensor_modes=[modes[i] for i in (16, 33, 36, 53)],
        geometry=geometry, working_firmware_format_decisions=formats,
        working_firmware_isp_choices=tuning, hardware_log_evidence=logged_evidence(),
        recorded_memory_layouts=logged_memory_overlap(),
        proposed_output=dict(width=5120, height=3840, megapixels=19.6608,
            output_yuv420_bytes=5120 * 3840 * 3 // 2,
            note='Design target only; output resizing and capture have not been implemented.'),
        findings={
            'memory': 'Full-height uncompressed raw + CE needs 125829120 bytes versus 31457280 today. Native arithmetic agrees with the saved captures.',
            'format': 'Working firmware selects qbc=1 for an 8192-wide raw input, versus qbc=0 for the current 4096-wide Live Photo input. The model itself was not executed.',
            'full_height': 'Mode 16 describes 8192x6144 at about 29.97 fps with Bayer code 0. The established ordinary full-resolution still uses mode 33, 15 fps and Bayer code 2. These are different readouts, not interchangeable settings.',
            'colour': 'ISP lookup results select a table only; table applicability to a new sensor readout and output colour cannot be established by software execution.',
            'table_audit_correction': 'Use all 621 registered ISP rows, confirmed at native registration 0x118f614. The prior 500-row audit missed ordinary full-resolution profiles. Exact ordinary baseline inputs reproduce row 616, normalshot_48M.',
            'memory_ownership': 'The recorded ordinary full-resolution raw + CE allocation overlaps the active Live Photo video bitstream reservation. It must not be reused as-is during video recording.',
            'pool_capacity': 'The recorded active Live Photo still pool cannot hold even full-height raw + CE plus the existing full-size intermediate YUV. A 20 MP final JPEG does not by itself reduce these earlier allocations.',
            'status': 'No full-height smooth-video + still capture configuration has been validated. No flashable candidate.'},
        limits=['Native control-flow and arithmetic only; no image quality proof.',
                '125829120 bytes is a raw + CE allocation, not the complete camera memory budget.',
                'Full-size intermediate YUV is an additional 75497472 bytes on the existing still path.',
                'Mode table frame rates are nominal, not measured performance.'])


if __name__ == '__main__':
    result = audit()
    output = ROOT / 'analysis/motion-resolution-audit/fullheight-path.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('geometry', 'working_firmware_format_decisions',
        'recorded_memory_layouts', 'findings')}, indent=2))
