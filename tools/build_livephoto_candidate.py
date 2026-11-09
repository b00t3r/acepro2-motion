#!/usr/bin/env python3
"""Build an OFFLINE Live Photo experiment; never deploys to a camera.

Capture compatibility remains unverified. Keep all partition and file lengths
unchanged, and independently verify exact decoded instruction/config changes.
"""
import argparse
import copy
import json
import struct
import zlib

import lz4.block
import lz4.frame

from build_usb_name_candidate import ROOT, SOURCES, unpack_package, repack, sha, USB_OFFSETS
from inspect_firmware import require, cstring


def literal_tail(data):
    n = len(data)
    result = bytearray([min(n, 15) << 4])
    if n >= 15:
        n -= 15
        result.extend(bytes([255]) * (n // 255))
        result.append(n % 255)
    result.extend(data)
    return bytes(result)


def compress_to_size(data, target):
    """Use a compressed prefix and an extended final literal sequence.

    No padding inside executable data or nonstandard frame trailer is needed.
    The LZ4 library must decode the exact expected block before acceptance.
    """
    def attempt(cut, compression_level):
        block = lz4.block.compress(data[:cut], mode='high_compression',
                                   compression=compression_level, store_size=False)
        p = 0
        while p < len(block):
            last = p
            token = block[p]
            p += 1
            length = token >> 4
            if length == 15:
                while True:
                    value = block[p]
                    p += 1
                    length += value
                    if value != 255:
                        break
            literal = p
            p += length
            if p == len(block):
                break
            p += 2
            if token & 15 == 15:
                while block[p] == 255:
                    p += 1
                p += 1
        return block[:last] + literal_tail(block[literal:] + data[cut:])

    # The compressed size is discrete: another HC level can fill a size gap
    # without changing any decoded bytes. Keep level 9 first for older builds.
    for compression_level in [9, 3, 6, 12]:
        lo, hi = 0, len(data)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if len(attempt(mid, compression_level)) > target:
                lo = mid
            else:
                hi = mid
        for cut in range(max(0, lo - 600), min(len(data), hi + 600) + 1):
            result = attempt(cut, compression_level)
            if len(result) == target:
                require(lz4.block.decompress(result, uncompressed_size=65536) == data,
                        'Same-length recompression changed decoded bytes')
                return result
    raise ValueError('Cannot preserve this compressed block length')


def edit_frame(frame, include_ui_fix=False, both_ui_states=False, still_crop=False, pixel_crop=False):
    before = lz4.frame.decompress(frame)
    after = bytearray(before)
    patches = [(0x369ea4 - 0x50000, '0008427a', '00e8427a'),
               (0x401540 - 0x50000, '7f3600b9', '7f6e0079')]
    require(not (include_ui_fix and both_ui_states), 'Select only one UI revision')
    require(not still_crop or both_ui_states, 'Still-crop trial requires both-state zoom UI fix')
    require(not pixel_crop or both_ui_states, 'Pixel-crop trial requires both-state zoom UI fix')
    require(not (still_crop and pixel_crop), 'Select one still-processing experiment')
    if both_ui_states:
        patches.append((0x55adec - 0x50000, 'ff0e0071', '0e000014'))
        if still_crop or pixel_crop:
            # PHOTO mode only: retain error/capability guards, skip inverse zoom guard.
            patches.append((0x55b034 - 0x50000, 'e10314aa', 'f3ffff17'))
        if still_crop:
            # RawPiv selected narrow but calculated its FOV from the wide context.
            patches.append((0x76c178 - 0x50000, '61185a79', '81de40b9'))
        if pixel_crop:
            from livephoto_geometry_patch import PATCHES
            patches.extend((address - 0x50000, old.hex(), new.hex())
                           for address, old, new in PATCHES)
        marker = (b'Insta360 Ace Pro V' if pixel_crop else
                  b'Insta360 Ace Pro Y' if still_crop else b'Insta360 Ace Pro Z')
        for offset in USB_OFFSETS:
            patches.append((offset, b'Insta360 Ace Pro 2'.hex(), marker.hex()))
    elif include_ui_fix:
        patches.append((0x55ae20 - 0x50000, '40feff54', '1f2003d5'))
    for offset, old, new in patches:
        old_bytes, new_bytes = bytes.fromhex(old), bytes.fromhex(new)
        require(len(old_bytes) == len(new_bytes), 'Patch length mismatch')
        require(after[offset:offset + len(old_bytes)] == old_bytes, 'Patch source mismatch')
        after[offset:offset + len(old_bytes)] = new_bytes
    result = bytearray(frame)
    cursor, base = 7, 0
    while True:
        encoded_size = struct.unpack_from('<I', frame, cursor)[0]
        cursor += 4
        if not encoded_size:
            break
        raw = bool(encoded_size & 0x80000000)
        size = encoded_size & 0x7fffffff
        block = frame[cursor:cursor + size]
        decoded = block if raw else lz4.block.decompress(block, uncompressed_size=65536)
        desired = bytes(after[base:base + len(decoded)])
        if desired != decoded:
            result[cursor:cursor + size] = desired if raw else compress_to_size(desired, size)
        cursor += size
        base += len(decoded)
    require(base == len(before) and cursor + 4 == len(frame), 'Unexpected LZ4 layout')
    checksum_frame = lz4.frame.compress(bytes(after), block_size=lz4.frame.BLOCKSIZE_MAX64KB,
                                       block_linked=False, content_checksum=True,
                                       block_checksum=False, store_size=False)
    result[cursor:cursor + 4] = checksum_frame[-4:]
    require(len(result) == len(frame), 'Frame length changed')
    require(lz4.frame.decompress(result) == after, 'Frame verification failed')
    return bytes(result), patches


def edit_settings(payload):
    require(struct.unpack_from('<I', payload)[0] == 0x66fc328a, 'Unexpected ROMFS')
    result = bytearray(payload)
    count = struct.unpack_from('<I', payload, 4)[0]
    found = []
    for i in range(count):
        entry = 8 + i * 76
        if cstring(payload[entry:entry + 64]) != 'camera_params.json':
            continue
        length, offset = struct.unpack_from('<II', payload, entry + 64)
        original = payload[offset:offset + length]
        before = json.loads(original)
        expected = copy.deepcopy(before)
        # First experiment is limited in the settings table to standard-lens
        # 16:9 Live Photo. The two code edits themselves are not mode-scoped.
        key = '4000_2250|true|STANDARD'
        options = expected['Iacwa586']['PHOTO_SINGLE']['undamage_zoom']['list']
        require(options[key] == ['false'], 'Unexpected existing zoom setting')
        options[key] = ['true', 'false']
        needle = ('"' + key + '":[\n"false"\n]').encode()
        require(original.count(needle) == 1, 'Ambiguous settings occurrence')
        edited = original.replace(needle, ('"' + key + '":["true","false"]').encode())
        # Remove only a few existing newlines to retain the exact file size.
        difference = len(edited) - length
        require(difference > 0 and edited.count(b'\n') >= difference, 'Unexpected settings size')
        edited = edited.replace(b'\n', b'', difference)
        require(len(edited) == length and json.loads(edited) == expected,
                'Settings changed beyond the single intended option')
        result[offset:offset + length] = edited
        struct.pack_into('<I', result, entry + 72, zlib.crc32(edited))
        found.append(key)
    require(len(found) == 1, 'Expected one camera settings file')
    return bytes(result), found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-ui-fix', action='store_true')
    parser.add_argument('--both-ui-states', action='store_true')
    parser.add_argument('--still-crop', action='store_true')
    parser.add_argument('--pixel-crop', action='store_true')
    args = parser.parse_args()
    for filename, expected in SOURCES.items():
        data = (ROOT / filename).read_bytes()
        require(sha(data) == expected, 'Original source changed')
        require(repack(unpack_package(data)) == data, 'Stock round-trip failed')
    original = (ROOT / 'Insta360AcePro2FW.bin').read_bytes()
    model = unpack_package(original)
    stock = copy.deepcopy(model)
    model['parts'][0]['payload'], patches = edit_frame(model['parts'][0]['payload'],
                                                      args.include_ui_fix, args.both_ui_states,
                                                      args.still_crop, args.pixel_crop)
    model['parts'][2]['payload'], keys = edit_settings(model['parts'][2]['payload'])
    candidate = repack(model)
    require(len(candidate) == len(original), 'Package length changed')
    checked = unpack_package(candidate)
    require(checked['parts'][1] == stock['parts'][1], 'DSP partition changed')
    require(checked['parts'][3] == stock['parts'][3], 'Device tree changed')
    require(checked['modules'][1:] == stock['modules'][1:], 'Non-CAM module changed')
    require(checked['parts'][0]['payload'] == model['parts'][0]['payload'], 'Main payload mismatch')
    require(checked['parts'][2]['payload'] == model['parts'][2]['payload'], 'Settings payload mismatch')
    out = ROOT / ('builds/offline-livephoto-pixels' if args.pixel_crop else
                  'builds/offline-livephoto-still' if args.still_crop else
                  'builds/offline-livephoto-ui-both' if args.both_ui_states else
                  'builds/offline-livephoto-ui' if args.include_ui_fix else 'builds/offline-livephoto')
    out.mkdir(exist_ok=True)
    path = out / 'Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin'
    path.write_bytes(candidate)
    require(path.read_bytes() == candidate, 'Candidate read-back failed')
    report = {'status': 'OFFLINE ONLY; capture compatibility unresolved; not approved for deployment',
              'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
              'size': len(candidate), 'patches': patches, 'settings_keys': keys,
              'usb_name': ('Insta360 Ace Pro V' if args.pixel_crop else
                           'Insta360 Ace Pro Y' if args.still_crop else
                           'Insta360 Ace Pro Z' if args.both_ui_states else 'Insta360 Ace Pro 2'),
              'rawpiv_effective_fov_input': args.still_crop,
              'inverse_livephoto_zoom_guard_bypassed_in_photo_mode': args.still_crop or args.pixel_crop,
              'livephoto_still_projection_canvas_correction': args.pixel_crop,
              'livephoto_enable_preserves_zoom_and_passes_support_check': args.pixel_crop,
              'same_partition_file_and_compressed_block_lengths': True,
              'camera_modified': False, 'recovery_procedure': 'unverified',
              'ui_state_one_warning_bypassed': args.include_ui_fix or args.both_ui_states,
              'ui_state_two_warning_retained': not args.both_ui_states,
              'limitations': ['Hardware and full capture lifecycle not emulated',
                              'Code edits affect other capture modes; settings edit is scoped',
                              'Still crop correction verified only through native parameter math; saved pixels require hardware validation',
                              'Supplied baseline is 4:3; initial settings experiment is 16:9']}
    (out / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Offline experimental candidate:', path)
    print('SHA256:', sha(candidate))
    print('Both originals round-trip; all original lengths retained. No camera writes.')


if __name__ == '__main__':
    main()
