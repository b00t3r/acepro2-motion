"""Build an offline Trial M, preserving the known-good V edits and package size."""
import hashlib
import json
import struct
import subprocess
from pathlib import Path
import lz4.block
import lz4.frame
from build_usb_name_candidate import ROOT, unpack_package, repack, USB_OFFSETS
from build_livephoto_candidate import compress_to_size

BASE = 0x50000
CAVE = 0x50240
CAVE_END = 0x51000
HOOK = 0x8bec48
OUT = ROOT / 'builds/offline-motion-photo'
SOURCE = ROOT / 'builds/offline-livephoto-pixels/Insta360AcePro2FW_LIVEPHOTO_EXPERIMENT.bin'
SOURCE_SHA = 'fd99de19dc472247d8e32521e8a7717c1989cfd7413bab18858b375a4572ad84'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_elf(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Expected little-endian AArch64 ELF64')
    shoff = struct.unpack_from('<Q', data, 40)[0]
    entsize, count, names_index = struct.unpack_from('<HHH', data, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*entsize) for i in range(count)]
    h = headers[names_index]
    names = data[h[4]:h[4]+h[5]]
    sections = []
    for h in headers:
        name = names[h[0]:].split(b'\0', 1)[0].decode()
        sections.append({'name': name, 'type': h[1], 'flags': h[2], 'offset': h[4],
                         'size': h[5], 'link': h[6], 'info': h[7], 'align': h[8],
                         'entry_size': h[9], 'data': data[h[4]:h[4]+h[5]]})
    symbols = []
    for sec in sections:
        if sec['type'] != 2:
            continue
        names = sections[sec['link']]['data']
        for p in range(0, sec['size'], 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', sec['data'], p)
            symbols.append({'name': names[name:].split(b'\0', 1)[0].decode(),
                            'section': index, 'value': value, 'size': size})
    return sections, symbols


def link_payload(paths):
    objects = [read_elf(p) for p in paths]
    blob = bytearray()
    locations, globals_ = {}, {}
    for oi, (sections, symbols) in enumerate(objects):
        for si, sec in enumerate(sections):
            if not sec['flags'] & 2 or not sec['size']:
                continue
            if sec['type'] != 1 or sec['flags'] & 1:
                raise ValueError('Payload may only contain initialized, read-only sections')
            align = max(sec['align'], 1)
            blob.extend(b'\0' * (-(CAVE+len(blob)) % align))
            locations[oi, si] = CAVE + len(blob)
            blob.extend(sec['data'])
        for sym in symbols:
            if sym['section'] and sym['name'] and not sym['name'].startswith('$'):
                globals_[sym['name']] = locations.get((oi, sym['section']), 0) + sym['value']
    relocations = []
    for oi, (sections, symbols) in enumerate(objects):
        for sec in sections:
            if sec['type'] != 4 or (oi, sec['info']) not in locations:
                continue
            for p in range(0, sec['size'], 24):
                offset, info, addend = struct.unpack_from('<QQq', sec['data'], p)
                sym = symbols[info >> 32]
                target = (locations[oi, sym['section']] + sym['value'] if sym['section']
                          else globals_[sym['name']]) + addend
                place = locations[oi, sec['info']] + offset
                at = place - CAVE
                kind = info & 0xffffffff
                w = struct.unpack_from('<I', blob, at)[0]
                if kind in (282, 283):  # JUMP26 / CALL26
                    delta = target - place
                    if delta % 4 or not -(1 << 27) <= delta < 1 << 27:
                        raise ValueError('Branch relocation overflow')
                    w = (w & 0xfc000000) | ((delta >> 2) & 0x3ffffff)
                elif kind == 275:  # ADR_PREL_PG_HI21
                    imm = ((target & ~4095) - (place & ~4095)) >> 12
                    if not -(1 << 20) <= imm < 1 << 20:
                        raise ValueError('ADRP relocation overflow')
                    w = (w & ~0x60ffffe0) | ((imm & 3) << 29) | (((imm >> 2) & 0x7ffff) << 5)
                elif kind == 277:  # ADD_ABS_LO12_NC
                    w = (w & ~0x003ffc00) | ((target & 4095) << 10)
                else:
                    raise ValueError(f'Unsupported ELF relocation {kind}')
                struct.pack_into('<I', blob, at, w)
                relocations.append({'kind': kind, 'place': hex(place), 'target': hex(target)})
    if CAVE + len(blob) > CAVE_END:
        raise ValueError(f'Payload exceeds zero gap: {len(blob)} > {CAVE_END-CAVE}')
    return bytes(blob), globals_, relocations


def edit_frame(frame, desired):
    original = lz4.frame.decompress(frame)
    chunks, cursor, base = [], 7, 0
    while True:
        size = struct.unpack_from('<I', frame, cursor)[0]
        cursor += 4
        if not size:
            break
        raw = bool(size & 0x80000000)
        size &= 0x7fffffff
        encoded = frame[cursor:cursor+size]
        decoded = encoded if raw else lz4.block.decompress(encoded, uncompressed_size=65536)
        target = desired[base:base+len(decoded)]
        changed = target != decoded
        if changed:
            encoded = lz4.block.compress(target, mode='high_compression', compression=12, store_size=False)
            raw = False
        chunks.append([encoded, raw, target, changed, size])
        base += len(decoded)
        cursor += size
    if base != len(original):
        raise ValueError('Unexpected LZ4 blocks')
    # Fund the new code by compressing a few ordinary blocks more efficiently.
    # Keep the total frame/partition/package lengths exactly as before.
    growth = sum(len(c[0])-c[4] for c in chunks)
    for index, c in enumerate(chunks):
        if growth <= 0:
            break
        if c[3] or c[1]:
            continue
        hc = lz4.block.compress(c[2], mode='high_compression', compression=12, store_size=False)
        saving = len(c[0]) - len(hc)
        if saving <= 0:
            continue
        if saving >= growth:
            try:
                exact = compress_to_size(c[2], len(c[0])-growth)
            except ValueError:
                # LZ4 sizes are discrete; another block may fill this budget.
                continue
            c[0] = exact
            growth = 0
        else:
            c[0] = hc
            growth -= saving
    if growth > 0:
        raise ValueError('Could not preserve frame length')
    if growth < 0:
        for c in chunks:
            if c[1]:
                continue
            try:
                exact = compress_to_size(c[2], len(c[0])-growth)
            except ValueError:
                continue
            c[0] = exact
            growth = 0
            break
        if growth < 0:
            raise ValueError('Could not fill exact frame length')
    check = lz4.frame.compress(desired, block_size=lz4.frame.BLOCKSIZE_MAX64KB,
                               block_linked=False, content_checksum=True, store_size=False)
    result = frame[:7] + b''.join(struct.pack('<I', len(c[0]) | (0x80000000 if c[1] else 0)) + c[0]
                                  for c in chunks) + b'\0'*4 + check[-4:]
    if len(result) != len(frame) or lz4.frame.decompress(result) != desired:
        raise ValueError('New LZ4 frame verification failed')
    return result


def main():
    OUT.mkdir(exist_ok=True)
    common = ['clang', '-target', 'aarch64-none-elf']
    subprocess.run(common + ['-Os', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                   '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
                   '-mgeneral-regs-only', '-c', str(ROOT/'tools/motion_photo_payload.c'),
                   '-o', str(OUT/'payload.o')], check=True)
    subprocess.run(common + ['-c', str(ROOT/'tools/motion_photo_entry.S'), '-o', str(OUT/'entry.o')], check=True)
    payload, symbols, relocations = link_payload([OUT/'entry.o', OUT/'payload.o'])
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Working trial V source mismatch')
    model = unpack_package(source)
    before = lz4.frame.decompress(model['parts'][0]['payload'])
    after = bytearray(before)
    if any(after[CAVE-BASE:CAVE_END-BASE]):
        raise ValueError('Code gap is not empty')
    if after[HOOK-BASE:HOOK-BASE+4] != bytes.fromhex('e04740f9'):
        raise ValueError('Hook source mismatch')
    after[CAVE-BASE:CAVE-BASE+len(payload)] = payload
    delta = symbols['motion_hook'] - HOOK
    struct.pack_into('<I', after, HOOK-BASE, 0x94000000 | ((delta >> 2) & 0x3ffffff))
    for offset in USB_OFFSETS:
        if after[offset:offset+18] != b'Insta360 Ace Pro V':
            raise ValueError('USB marker source mismatch')
        after[offset:offset+18] = b'Insta360 Ace Pro M'
    model['parts'][0]['payload'] = edit_frame(model['parts'][0]['payload'], bytes(after))
    candidate = repack(model)
    if len(candidate) != len(source):
        raise ValueError('Package length changed')
    checked = unpack_package(candidate)
    if lz4.frame.decompress(checked['parts'][0]['payload']) != after:
        raise ValueError('Packaged image mismatch')
    stock_model = unpack_package(source)
    if checked['parts'][1:] != stock_model['parts'][1:]:
        raise ValueError('Non-main partitions changed')
    path = OUT/'Insta360AcePro2_v2.0.51_LivePhoto-2x_Extra-MotionPhoto_Trial-M.bin'
    path.write_bytes(candidate)
    (OUT/'payload.bin').write_bytes(payload)
    (OUT/'main_threadx.bin').write_bytes(after)
    report = {'status': 'OFFLINE candidate; native mocked tests pending; not staged',
              'path': str(path), 'sha256': sha(candidate), 'size': len(candidate),
              'source_sha256': SOURCE_SHA, 'usb_name': 'Insta360 Ace Pro M',
              'hook': hex(HOOK), 'code_gap': [hex(CAVE), hex(CAVE_END)],
              'payload_bytes': len(payload), 'symbols': symbols, 'relocations': relocations,
              'original_media_preserved': True, 'hardware_verified': False,
              'format': 'Same modern XMP + exact original JPEG/LRV as phone-tested Candidate05',
              'output_filename': 'Original LIV stem + .MP.jpg',
              'errors': 'Partial files remain .MP.tmp; existing .MP.jpg and .MP.tmp skipped'}
    (OUT/'build_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('relocations','symbols')}, indent=2))


if __name__ == '__main__':
    main()
