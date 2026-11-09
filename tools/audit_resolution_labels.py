"""Decode native English resolution strings; no firmware or camera changes."""
import json
import re
import struct
from pathlib import Path

from livephoto_harness import Harness, CONTEXT, ROOT, RETURN, image
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30


def audit():
    data = image()
    resources = (ROOT / 'analysis/extracted/ewres.bin').read_bytes()
    chunks = {}
    # A localized string record is language:u32, padding, chunk:u64,
    # decoded-halfword-offset:u16, padding. English is language 0, as
    # confirmed by the existing native zoom-warning regression test.
    for off in range(8, len(data) - 16, 8):
        pointer = struct.unpack_from('<Q', data, off)[0]
        # The numeric labels also have direct, unlocalized descriptors
        # (chunk pointer + halfword index), without a language record.
        if pointer != 0x3f3eef8 and struct.unpack_from('<I', data, off - 8)[0] != 0:
            continue
        relative = pointer - 0x3ea4f40
        if not 0 <= relative < len(resources) - 4:
            continue
        size = struct.unpack_from('<I', resources, relative)[0]
        index = struct.unpack_from('<H', data, off + 8)[0]
        if 0 < size < 0x4000 and index * 2 < size:
            chunks.setdefault(pointer, []).append(off + 0x50000)
    h = Harness()
    h.uc.mem_map(0x12749000, 0x1000)
    h.uc.mem_write(0x12749c40, struct.pack('<Q', CONTEXT + 0x10000))
    labels = []
    for pointer, records in chunks.items():
        relative = pointer - 0x3ea4f40
        size = struct.unpack_from('<I', resources, relative)[0]
        h.uc.mem_write(CONTEXT + 0x1000, resources[relative + 4:relative + 0x4000])
        h.uc.mem_write(CONTEXT + 0x8000, bytes(0x4000))
        h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT + 0x1000)
        h.uc.reg_write(UC_ARM64_REG_X1, CONTEXT + 0x8000)
        h.uc.reg_write(UC_ARM64_REG_X30, RETURN)
        h.outcome = None
        h.run(0x4650c0, max_instructions=300000)
        decoded = bytes(h.uc.mem_read(CONTEXT + 0x8000, size))
        for record in records:
            index = struct.unpack_from('<H', data, record - 0x50000 + 8)[0]
            if index * 2 >= size:
                continue
            text = decoded[index * 2:].decode('utf-16le', errors='replace').split('\0')[0]
            if len(text) < 40 and ('MP' in text or re.fullmatch(r'[\d.]+M?', text)):
                labels.append(dict(pointer_field=hex(record), chunk=hex(pointer),
                                   halfword_index=index, text=text))
    return dict(english_chunks_decoded=len(chunks), labels=labels,
                hardware_executed=False, firmware_changed=False)


if __name__ == '__main__':
    report = audit()
    path = ROOT / 'analysis/motion-resolution-audit/resolution-labels.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
