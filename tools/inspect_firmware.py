#!/usr/bin/env python3
"""Read-only inspector for the observed Ace Pro 2 update format.

Offsets and record layouts are reverse engineered from the supplied image.
This is an extractor, not a repacker or flashing tool. CRC/MD5 validate
integrity only; they do not establish whether the camera requires signatures.
"""
import argparse
import array
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path

import lz4.frame
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def cstring(data):
    return data.split(b'\0', 1)[0].decode('utf-8', errors='replace')


def strings(data):
    for m in re.finditer(rb'[\x20-\x7e]{5,}', data):
        yield m.start(), m.group().decode('ascii')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_dtb(data):
    fields = struct.unpack_from('>10I', data)
    magic, total, pos, strbase = fields[:4]
    require(magic == 0xd00dfeed and total == len(data), 'Bad DTB header')
    stack, props = [], []
    while pos < total:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(cstring(data[pos:end]))
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', data, pos)
            pos += 8
            raw = data[pos:pos + size]
            require(len(raw) == size, 'Truncated DTB property')
            name = cstring(data[strbase + nameoff:])
            value = raw.hex()
            if raw and raw[-1] == 0 and all(x == 0 or 32 <= x < 127 for x in raw):
                value = raw[:-1].decode().split('\0')
            props.append({'path': '/' + '/'.join(stack[1:]), 'name': name,
                          'value': value})
            pos = (pos + size + 3) & ~3
        elif token == 9:
            return props
        elif token != 4:
            raise ValueError('Unexpected DTB token')
    raise ValueError('Missing DTB end token')


def find_refs(data, base, targets, lookahead=4):
    """Find nearby ADRP + ADD address formation. Not a full dataflow analysis."""
    words = array.array('I', data[:len(data) & ~3])
    if sys.byteorder != 'little':
        words.byteswap()
    bypage = {}
    for label, offset in targets.items():
        bypage.setdefault((base + offset) & ~4095, []).append((label, base + offset))
    found = []
    for i, word in enumerate(words):
        if word & 0x9f000000 != 0x90000000:
            continue
        imm = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
        if imm & (1 << 20):
            imm -= 1 << 21
        page = ((base + i * 4) & ~4095) + (imm << 12)
        if page not in bypage:
            continue
        reg = word & 31
        for j in range(i + 1, min(i + 1 + lookahead, len(words))):
            add = words[j]
            if add & 0xffc00000 != 0x91000000 or (add >> 5) & 31 != reg:
                continue
            address = page + ((add >> 10) & 4095)
            for label, target in bypage[page]:
                if address == target:
                    found.append({'label': label, 'file_offset': i * 4,
                                  'address': base + i * 4, 'add_offset': j * 4})
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', nargs='?', default='Insta360AcePro2FW.bin')
    parser.add_argument('--out', default='analysis')
    args = parser.parse_args()
    source, out = Path(args.firmware).resolve(), Path(args.out).resolve()
    require(source != out and source not in out.parents, 'Output must not be inside input')
    data = source.read_bytes()
    extracted = out / 'extracted'
    extracted.mkdir(parents=True, exist_ok=True)
    manifest = {'source': source.name, 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}

    # Final 32 bytes: magic, module count, reserved, whole-prefix MD5.
    footer = len(data) - 32
    require(data[footer:footer + 8] == b'WFNITOPS', 'Unrecognized footer magic')
    count = u32(data, footer + 8)
    require(0 < count <= 32, 'Invalid module count')
    require(hashlib.md5(data[:-16]).digest() == data[-16:], 'Package MD5 mismatch')
    table = footer - count * 84
    require(table >= 0, 'Invalid module table')
    manifest['package_md5_valid'] = True
    manifest['footer_offset'] = footer
    manifest['module_table_offset'] = table
    modules, cursor = [], 0
    for i in range(count):
        p = table + i * 84
        size = u32(data, p)
        name, version = cstring(data[p + 4:p + 36]), cstring(data[p + 36:p + 68])
        require(cursor + size <= table, 'Module exceeds payload')
        payload = data[cursor:cursor + size]
        require(hashlib.md5(payload).digest() == data[p + 68:p + 84], 'Module MD5 mismatch')
        modules.append({'name': name, 'version': version, 'offset': cursor,
                        'size': size, 'md5_valid': True})
        if name == 'MCU':
            (extracted / 'mcu.bin').write_bytes(payload)
        elif name == 'CAMBLD':
            (extracted / 'cam_bootloader_package.bin').write_bytes(payload)
        cursor += size
    require(cursor == table, 'Unaccounted bytes before module table')
    require(modules[0]['name'] == 'CAM', 'Expected CAM first')
    manifest['modules'] = modules

    # Candidate partition definitions in the CAM header; declared slots are not
    # necessarily present as payloads in this update.
    declared = []
    for p in range(0xd8, 0x538, 40):
        name = cstring(data[p:p + 32])
        if name:
            declared.append({'name': name, 'attributes_raw': u32(data, p + 32),
                             'capacity_raw': u32(data, p + 36)})
    manifest['declared_partitions'] = declared
    partitions, romfiles = [], []
    cursor = 0x5b0
    main_image = None
    # Observed payload sequence, labels inferred from contents/header slots.
    cumulative_crc = 0
    for label, index_offset in zip(['main_threadx', 'dsp_romfs', 'system_romfs', 'device_tree'],
                                   [0x30, 0x38, 0x40, 0x98]):
        header = struct.unpack_from('<8I', data, cursor)
        crc, version, date, size, load = header[:5]
        start, end = cursor + 256, cursor + 256 + size
        require(end <= modules[0]['size'], 'Partition exceeds CAM module')
        payload = data[start:end]
        require(zlib.crc32(payload) == crc, 'Partition CRC mismatch: ' + label)
        indexed_size, indexed_crc = struct.unpack_from('<II', data, index_offset)
        require(indexed_size == 256 + size, 'Indexed partition size mismatch: ' + label)
        cumulative_crc = zlib.crc32(data[cursor:end], cumulative_crc)
        require(indexed_crc == (cumulative_crc ^ 0xffffffff),
                'Cumulative partition CRC mismatch: ' + label)
        record = {'label': label, 'header_offset': cursor, 'payload_offset': start,
                  'size': size, 'crc32': f'{crc:08x}', 'crc32_valid': True,
                  'header_words': list(header), 'load_address_raw': load,
                  'date_raw': f'{date:08x}'}
        record['cumulative_crc_valid'] = True
        if label == 'main_threadx':
            main_image, consumed = lz4.frame.decompress(payload, return_bytes_read=True)
            require(consumed == size, 'Unexpected bytes after LZ4 frame')
            record['decompressed_size'] = len(main_image)
            (extracted / 'main_threadx.bin').write_bytes(main_image)
        elif label == 'device_tree':
            (extracted / 'device_tree.dtb').write_bytes(payload)
            (out / 'device_tree.json').write_text(json.dumps(parse_dtb(payload), indent=2) + '\n')
        else:
            require(u32(payload, 0) == 0x66fc328a, 'Bad ROMFS magic')
            filecount = u32(payload, 4)
            require(8 + filecount * 76 <= len(payload), 'ROMFS table out of bounds')
            record['romfs_file_count'] = filecount
            for i in range(filecount):
                p = 8 + i * 76
                name = cstring(payload[p:p + 64])
                length, offset, expected_crc = struct.unpack_from('<3I', payload, p + 64)
                require(offset >= 8 + filecount * 76 and offset + length <= len(payload), 'Bad ROMFS file bounds')
                content = payload[offset:offset + length]
                require(zlib.crc32(content) == expected_crc, 'ROMFS CRC mismatch: ' + name)
                romfiles.append({'partition': label, 'name': name, 'size': length,
                                 'partition_offset': offset, 'firmware_offset': start + offset,
                                 'crc32': f'{expected_crc:08x}', 'crc32_valid': True})
                if name in {'aiisp_rtos.bin', 'aiisp_config.bin', 'camera_params.json'}:
                    (extracted / name).write_bytes(content)
        partitions.append(record)
        cursor = end
    require(cursor == modules[0]['size'], 'Unaccounted CAM bytes')
    require(u32(data, 0x24) == cumulative_crc, 'CAM cumulative CRC mismatch')
    manifest['cam_cumulative_crc_valid'] = True
    manifest['partitions'] = partitions
    manifest['romfs_file_count'] = len(romfiles)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'romfs_files.json').write_text(json.dumps(romfiles, indent=2) + '\n')

    patterns = {
        'os': r'OS: ThreadX|threadxA64|RT-Thread|rt-thread/rt-thread|cv5_sdk',
        'debug': r'AmbaShell|cdc_acm_shell|CdcAcmd|svc_auto_run\.ash|cvexec\.ash|uart baudrate|Usage: aip|\[Unittest\] Add shell',
        'update': r'FWPKG|FWUpdate_Check_MD5|FW File MD5|File %s MD5|ImageCRC32|CRC32|FwUpdater_WriteDtb|secure.?boot|OTP_.*PUKEY',
    }
    for group, pattern in patterns.items():
        rx = re.compile(pattern, re.I)
        lines = []
        for filename in ['main_threadx.bin', 'aiisp_rtos.bin', 'mcu.bin']:
            path = extracted / filename
            if path.exists():
                lines.extend(f'{filename}:0x{o:08x}\t{s}' for o, s in strings(path.read_bytes()) if rx.search(s))
        (out / f'evidence_{group}.tsv').write_text('\n'.join(lines) + '\n')

    targets = {}
    for term in [b':\\svc_auto_run.ash', b':\\cvexec.ash', b'OS: ThreadX 64-bit',
                 b'FW File MD5 Check Fail.', b'AppCdcAcmd_Start(): Broken Shell starts.']:
        offset = main_image.find(term)
        if offset >= 0:
            targets[term.decode()] = offset
    refs = find_refs(main_image, partitions[0]['load_address_raw'], targets)
    (out / 'string_references.json').write_text(json.dumps(refs, indent=2) + '\n')
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    listing = []
    for ref in refs:
        offset = ref['file_offset']
        start, end = max(0, offset - 32), ref['add_offset'] + 96
        listing.append(f"\n# {ref['label']} | decompressed file offset 0x{offset:x}")
        listing.extend(f'{i.address:016x}  {i.mnemonic:8s} {i.op_str}'
                       for i in md.disasm(main_image[start:end], partitions[0]['load_address_raw'] + start))
    (out / 'references_aarch64.txt').write_text('\n'.join(listing) + '\n')
    # Follow-up function boundaries established by manual inspection of this
    # exact image. Do not apply these addresses to another firmware revision.
    if manifest['sha256'] == '9b5b98818a05b7e9d95dad00990ad0c8e978aa59de80867d6fc59010d5cb7094':
        ranges = [('script_path_and_check', 0x1617000, 0x16170e4),
                  ('storage_monitor', 0x1617100, 0x16175c0),
                  ('script_reader', 0x1617c20, 0x1617e2c),
                  ('shell_execution_wrapper', 0xdcdf40, 0xdcdf74)]
        listing = []
        base = partitions[0]['load_address_raw']
        for label, start, end in ranges:
            listing.append(f'\n# {label}; VA 0x{start:x}, decompressed offset 0x{start-base:x}')
            listing.extend(f'{i.address:016x}  {i.mnemonic:8s} {i.op_str}'
                           for i in md.disasm(main_image[start-base:end-base], start))
        (out / 'startup_script_aarch64.txt').write_text('\n'.join(listing) + '\n')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == manifest['sha256'], 'Source changed during analysis')
    print(f"Verified {count} modules, {len(partitions)} partition CRCs, {len(romfiles)} ROMFS file CRCs and LZ4 frame checksums.")
    print(f'Found {len(refs)} candidate ARM64 string references. Original SHA256: {manifest["sha256"]}')
    print('Results:', out)


if __name__ == '__main__':
    main()
