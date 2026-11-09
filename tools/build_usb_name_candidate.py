#!/usr/bin/env python3
"""Build a same-size OFFLINE experimental update. Never deploys or flashes.

Preserves original compressed blocks; edits one LZ4 literal and regenerates
the frame content checksum and known container integrity fields. Both stock
packages must round-trip byte-for-byte before a candidate can be written.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

import lz4.block
import lz4.frame

from inspect_firmware import require, cstring

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    'Insta360AcePro2FW.bin': '9b5b98818a05b7e9d95dad00990ad0c8e978aa59de80867d6fc59010d5cb7094',
    'Insta360AcePro2FW.bin.old.bin': '6ad878a7e756ea0e68627ecd2bb016dd4f5405b625e795dc6b7ab9355327a9aa',
}
OLD_NAME = b'Insta360 Ace Pro 2'
NEW_NAME = b'Insta360 Ace Pro X'
USB_OFFSETS = [0x3336ed5, 0x3338ed5, 0x3338ef3, 0x3338f09]
INDEX_OFFSETS = [0x30, 0x38, 0x40, 0x98]


def md5(data):
    return hashlib.md5(data).digest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack_package(data):
    require(data[-32:-24] == b'WFNITOPS', 'Unknown package footer')
    require(md5(data[:-16]) == data[-16:], 'Input package digest mismatch')
    count = struct.unpack_from('<I', data, len(data) - 24)[0]
    require(count in (2, 3), 'Unexpected module count')
    table = len(data) - 32 - count * 84
    modules, cursor = [], 0
    for i in range(count):
        record = data[table + i * 84:table + (i + 1) * 84]
        size = struct.unpack_from('<I', record)[0]
        require(cursor + size <= table, 'Module exceeds package data')
        payload = data[cursor:cursor + size]
        require(md5(payload) == record[68:84], 'Module digest mismatch')
        modules.append({'name': cstring(record[4:36]), 'record': record, 'payload': payload})
        cursor += size
    require(cursor == table and modules[0]['name'] == 'CAM', 'Unexpected module layout')
    cam = modules[0]['payload']
    cursor, parts, running = 0x5b0, [], 0
    for field in INDEX_OFFSETS:
        header = cam[cursor:cursor + 256]
        require(len(header) == 256, 'Truncated partition header')
        expected, _, _, size = struct.unpack_from('<4I', header)
        payload = cam[cursor + 256:cursor + 256 + size]
        require(len(payload) == size and zlib.crc32(payload) == expected, 'Partition CRC mismatch')
        indexed_size, indexed_crc = struct.unpack_from('<II', cam, field)
        require(indexed_size == size + 256, 'Indexed length mismatch')
        running = zlib.crc32(header + payload, running)
        require(indexed_crc == running ^ 0xffffffff, 'Indexed cumulative CRC mismatch')
        parts.append({'header': header, 'payload': payload})
        cursor += 256 + size
    require(cursor == len(cam), 'Unaccounted CAM bytes')
    require(struct.unpack_from('<I', cam, 0x24)[0] == running, 'CAM CRC mismatch')
    return {'header': cam[:0x5b0], 'parts': parts, 'modules': modules,
            'footer': data[-32:-16]}


def repack(model):
    header = bytearray(model['header'])
    pieces, running = [], 0
    for field, part in zip(INDEX_OFFSETS, model['parts']):
        pheader = bytearray(part['header'])
        payload = part['payload']
        # Same-size only: unknown length-related metadata remains valid.
        require(struct.unpack_from('<I', pheader, 12)[0] == len(payload), 'Length-changing edits are unsupported')
        struct.pack_into('<I', pheader, 0, zlib.crc32(payload))
        piece = bytes(pheader) + payload
        running = zlib.crc32(piece, running)
        struct.pack_into('<II', header, field, len(piece), running ^ 0xffffffff)
        pieces.append(piece)
    struct.pack_into('<I', header, 0x24, running)
    cam = bytes(header) + b''.join(pieces)
    payloads, records = [], []
    for i, module in enumerate(model['modules']):
        payload = cam if i == 0 else module['payload']
        record = bytearray(module['record'])
        struct.pack_into('<I', record, 0, len(payload))
        record[68:84] = md5(payload)
        payloads.append(payload)
        records.append(bytes(record))
    prefix = b''.join(payloads) + b''.join(records) + model['footer']
    return prefix + md5(prefix)


def decode_frame_blocks(frame):
    require(frame[:7] == bytes.fromhex('04224d186440a7'), 'Unexpected LZ4 frame settings')
    cursor, chunks = 7, []
    while True:
        size = struct.unpack_from('<I', frame, cursor)[0]
        cursor += 4
        if size == 0:
            break
        raw = bool(size & 0x80000000)
        size &= 0x7fffffff
        require(cursor + size <= len(frame), 'Truncated compressed block')
        block = frame[cursor:cursor + size]
        chunks.append(block if raw else lz4.block.decompress(block, uncompressed_size=65536))
        cursor += size
    require(cursor + 4 == len(frame), 'Unexpected frame trailer')
    return b''.join(chunks), cursor


def main():
    results = {}
    for filename, expected in SOURCES.items():
        source = (ROOT / filename).read_bytes()
        require(sha(source) == expected, 'Source hash changed: ' + filename)
        model = unpack_package(source)
        rebuilt = repack(model)
        require(rebuilt == source, 'Stock round-trip is not byte-identical: ' + filename)
        results[filename] = {'byte_identical': True, 'sha256': sha(rebuilt), 'size': len(rebuilt)}
        del source, model, rebuilt

    original = (ROOT / 'Insta360AcePro2FW.bin').read_bytes()
    model = unpack_package(original)
    original_frame = model['parts'][0]['payload']
    main_before = lz4.frame.decompress(original_frame)
    require(original_frame.count(OLD_NAME) == 1, 'Expected one compressed literal')
    frame = bytearray(original_frame)
    literal = frame.index(OLD_NAME)
    require(len(NEW_NAME) == len(OLD_NAME), 'USB name must retain its length')
    frame[literal:literal + len(OLD_NAME)] = NEW_NAME
    main_after, trailer = decode_frame_blocks(bytes(frame))
    # Ask the installed LZ4 library to produce the content checksum. Its
    # temporary recompressed blocks are discarded; original blocks are kept.
    checksum_frame = lz4.frame.compress(
        main_after, block_size=lz4.frame.BLOCKSIZE_MAX64KB, block_linked=False,
        content_checksum=True, block_checksum=False, store_size=False)
    frame[trailer:trailer + 4] = checksum_frame[-4:]
    require(lz4.frame.decompress(frame) == main_after, 'Patched frame checksum/decode failed')
    require(len(main_before) == len(main_after), 'Main image size changed')
    expected_offsets = [offset + len(OLD_NAME) - 1 for offset in USB_OFFSETS]
    changed = [i for i, (a, b) in enumerate(zip(main_before, main_after)) if a != b]
    require(changed == expected_offsets, 'Compressed edit propagated beyond the four expected USB strings')
    for offset in USB_OFFSETS:
        require(main_before[offset:offset + len(OLD_NAME)] == OLD_NAME, 'Original USB string mismatch')
        require(main_after[offset:offset + len(NEW_NAME)] == NEW_NAME, 'New USB string mismatch')
        require(main_before[offset - 4:offset - 1] in (b'\x09\x04\x02', b'\x09\x04\x04', b'\x09\x04\x05'),
                'Unexpected USB string descriptor prefix')
    require(len(frame) == len(original_frame), 'Compressed frame size changed')
    model['parts'][0]['payload'] = bytes(frame)
    candidate = repack(model)
    require(len(candidate) == len(original), 'Update package size changed')
    checked = unpack_package(candidate)
    # Preserve every non-main payload, header, module, and all unknown header
    # fields. Restrict complete-package differences to explicitly known bytes.
    allowed = set(range(0x24, 0x28)) | set(range(0x5b0, 0x5b4))
    for field in INDEX_OFFSETS:
        allowed.update(range(field + 4, field + 8))
    allowed.add(0x6b0 + literal + len(OLD_NAME) - 1)
    allowed.update(range(0x6b0 + trailer, 0x6b0 + trailer + 4))
    table = len(candidate) - 32 - len(model['modules']) * 84
    allowed.update(range(table + 68, table + 84))
    allowed.update(range(len(candidate) - 16, len(candidate)))
    package_changes = [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
    require(set(package_changes) <= allowed, 'Unexpected complete-package change')
    for oldpart, newpart in zip(unpack_package(original)['parts'][1:], checked['parts'][1:]):
        require(oldpart == newpart, 'Non-main partition changed')
    for oldmod, newmod in zip(model['modules'][1:], checked['modules'][1:]):
        require(oldmod == newmod, 'Non-CAM module changed')
    out = ROOT / 'builds/offline-usb-name'
    out.mkdir(parents=True, exist_ok=True)
    output = out / 'Insta360AcePro2FW_USB_NAME_TEST.bin'
    require(output.resolve() not in [(ROOT / x).resolve() for x in SOURCES], 'Would overwrite source')
    output.write_bytes(candidate)
    require(output.read_bytes() == candidate, 'Candidate read-back failed')
    report = {'status': 'OFFLINE CANDIDATE; NOT FLASH-VALIDATED',
              'camera_modified': False, 'source_sha256': sha(original),
              'candidate_sha256': sha(candidate), 'candidate_file': output.name,
              'size': len(candidate), 'stock_roundtrips': results,
              'old_usb_name': OLD_NAME.decode(), 'new_usb_name': NEW_NAME.decode(),
              'decompressed_main_changed_offsets': changed,
              'compressed_literal_offset_in_frame': literal,
              'total_package_changed_bytes': len(package_changes),
              'package_changes': [{'offset': i, 'before': original[i], 'after': candidate[i]}
                                  for i in package_changes],
              'all_changes_within_allowlist': True,
              'non_main_partitions_identical': True, 'mcu_module_identical': True,
              'signature_enforcement': 'unknown', 'recovery_procedure': 'unverified'}
    (out / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    for filename, expected in SOURCES.items():
        require(sha((ROOT / filename).read_bytes()) == expected, 'Original source changed')
    print('Both stock packages round-trip byte-for-byte.')
    print('Candidate:', output)
    print('Decompressed main image: exactly four bytes changed in USB string descriptors.')
    print('Complete package:', len(package_changes), 'changed bytes, all explicitly allowed.')
    print('No deployment or flashing performed.')


if __name__ == '__main__':
    main()
