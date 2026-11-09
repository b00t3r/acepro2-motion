#!/usr/bin/env python3
"""Extract and document the known 2.0.50 CAMBLD package without executing it."""
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from inspect_firmware import find_refs, require, strings

ROOT = Path(__file__).resolve().parent.parent


def main():
    source = ROOT / 'Insta360AcePro2FW.bin.old.bin'
    data = source.read_bytes()
    require(hashlib.sha256(data).hexdigest() ==
            '6ad878a7e756ea0e68627ecd2bb016dd4f5405b625e795dc6b7ab9355327a9aa',
            'This analysis uses addresses established for the supplied 2.0.50 package only')
    manifest = json.loads((ROOT / 'analysis/previous/manifest.json').read_text())
    module = next(x for x in manifest['modules'] if x['name'] == 'CAMBLD')
    pkg = data[module['offset']:module['offset'] + module['size']]
    extracted = ROOT / 'analysis/previous/extracted'
    extracted.mkdir(parents=True, exist_ok=True)
    summary = {'source_sha256': hashlib.sha256(data).hexdigest(),
               'bootloader_version_label': module['version'],
               'installed_bootloader_version': 'unknown', 'sections': []}
    cursor = 0x5b0
    for label in ['bootstrap', 'bootloader']:
        crc, version, date, size, load, _, _, _ = struct.unpack_from('<8I', pkg, cursor)
        start, end = cursor + 256, cursor + 256 + size
        require(end <= len(pkg), 'Section exceeds CAMBLD package')
        payload = pkg[start:end]
        require(zlib.crc32(payload) == crc, 'Section CRC mismatch')
        (extracted / f'{label}.bin').write_bytes(payload)
        summary['sections'].append({'label': label, 'package_header_offset': cursor,
                                    'package_payload_offset': start,
                                    'original_file_offset': module['offset'] + start,
                                    'size': size, 'load_address': load,
                                    'crc32': f'{crc:08x}', 'crc32_valid': True,
                                    'sha256': hashlib.sha256(payload).hexdigest()})
        cursor = end
    require(cursor == len(pkg), 'Unaccounted CAMBLD bytes')
    boot = (extracted / 'bootloader.bin').read_bytes()
    base = summary['sections'][1]['load_address']
    require(base == 0x10000000, 'Unexpected bootloader load address')
    targets = {s: o for o, s in strings(boot)
               if re.search(r'(?i)Load Firmware|Updater image|Load Kernel|Kernel image|Boot failed|Enter Kernel|backup XTB|amboot>|Watchdog test|WDT reset', s)}
    refs = find_refs(boot, base, targets)
    out = ROOT / 'analysis'
    (out / 'bootloader_string_refs.json').write_text(json.dumps(refs, indent=2) + '\n')
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    ranges = [
        ('boot_main', 0x10002220, 0x10002388),
        ('partition_selection_and_load', 0x10001980, 0x100020e0),
        ('boot_handoff_and_returned_failure', 0x100020e0, 0x1000220c),
        ('updater_flag_comparison', 0x1000c440, 0x1000c484),
        ('crc_mismatch_handler', 0x10001100, 0x1000117c),
        ('watchdog_gated_partition_switch', 0x100043c0, 0x10004654),
        ('crc32_wrapper', 0x10004ee0, 0x10004f0c),
        ('hardware_crc32_helpers', 0x10005da0, 0x10005ddc),
        ('uart_console_entry', 0x10003c20, 0x10003d30),
    ]
    lines = []
    for label, start, end in ranges:
        lines.append(f'\n# {label}: VA 0x{start:x}, extracted offset 0x{start-base:x}')
        lines.extend(f'{i.address:016x}  {i.mnemonic:8s} {i.op_str}'
                     for i in md.disasm(boot[start-base:end-base], start))
    (out / 'bootloader_recovery_aarch64.txt').write_text('\n'.join(lines) + '\n')
    md.skipdata = True
    (out / 'bootloader_linear_aarch64.txt').write_text(
        '# Linear decode with skip-data: data regions may decode as instructions.\n' +
        '\n'.join(f'{i.address:016x}  {i.mnemonic:8s} {i.op_str}'
                  for i in md.disasm(boot, base)) + '\n')
    (out / 'bootloader_strings.tsv').write_text(
        '\n'.join(f'0x{base+o:08x}\t{s}' for o, s in strings(boot)) + '\n')
    app = (ROOT / 'analysis/extracted/main_threadx.bin').read_bytes()
    app_lines = []
    md.skipdata = False
    for label, start, end in [('set_updater_flag', 0x2fcda0, 0x2fd080),
                              ('package_digest_check', 0x359900, 0x359a8c)]:
        app_lines.append(f'\n# 2.0.51 {label}: VA 0x{start:x}; image base 0x50000')
        app_lines.extend(f'{i.address:016x}  {i.mnemonic:8s} {i.op_str}'
                         for i in md.disasm(app[start-0x50000:end-0x50000], start))
    (out / 'update_flag_and_digest_aarch64.txt').write_text('\n'.join(app_lines) + '\n')
    summary['function_ranges'] = [{'label': n, 'start_va': a, 'end_va': b}
                                  for n, a, b in ranges]
    summary['updater_selection'] = {
        'function_va': 0x1000c440,
        'comparison': '32-bit word at 0x110 equals active user partition table word at +4',
        'equal_branch': 'XTB/backup-XTB processing followed by system partition 2 FW_UPDATER',
        'unequal_branch': 'user partition 1 SYS_SW main image'}
    (out / 'bootloader_manifest.json').write_text(json.dumps(summary, indent=2) + '\n')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == summary['source_sha256'],
            'Original changed during analysis')
    print('Verified and extracted bootstrap (16,384 bytes) and bootloader (83,456 bytes).')
    print('Saved targeted recovery listings, strings, references, and manifest. Source is unchanged.')


if __name__ == '__main__':
    main()
