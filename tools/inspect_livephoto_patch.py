#!/usr/bin/env python3
"""Check whether proposed code edits can safely reuse stock LZ4 literals.

Read-only: does not build an update or access a camera. LZ4 match copies can
make one compressed-byte edit alter multiple decompressed instructions.
"""
import json
import struct

import lz4.block

from build_usb_name_candidate import ROOT, SOURCES, sha, unpack_package
from inspect_firmware import require


def decode_origins(block, raw=False):
    if raw:
        return block, list(range(len(block)))
    out, origins, p = bytearray(), [], 0
    while p < len(block):
        token = block[p]
        p += 1
        literal_length = token >> 4
        if literal_length == 15:
            while True:
                value = block[p]
                p += 1
                literal_length += value
                if value != 255:
                    break
        require(p + literal_length <= len(block), 'Truncated literal')
        out.extend(block[p:p + literal_length])
        origins.extend(range(p, p + literal_length))
        p += literal_length
        if p == len(block):
            break
        distance = int.from_bytes(block[p:p + 2], 'little')
        p += 2
        require(0 < distance <= len(out), 'Invalid match distance')
        match_length = (token & 15) + 4
        if token & 15 == 15:
            while True:
                value = block[p]
                p += 1
                match_length += value
                if value != 255:
                    break
        require(len(out) + match_length <= 65536, 'Decoded block too large')
        for _ in range(match_length):
            out.append(out[-distance])
            origins.append(origins[-distance])
    result = bytes(out)
    require(result == lz4.block.decompress(block, uncompressed_size=65536),
            'Origin decoder differs from library')
    return result, origins


def inspect_edits(frame, patches):
    wanted = {offset + i: value for offset, patch in patches.items()
              for i, value in enumerate(patch)}
    cursor, base, results = 7, 0, []
    seen = set()
    while True:
        encoded_size = struct.unpack_from('<I', frame, cursor)[0]
        cursor += 4
        if not encoded_size:
            break
        raw = bool(encoded_size & 0x80000000)
        size = encoded_size & 0x7fffffff
        block = frame[cursor:cursor + size]
        decoded = block if raw else lz4.block.decompress(block, uncompressed_size=65536)
        selected = {offset - base: value for offset, value in wanted.items()
                    if base <= offset < base + len(decoded) and decoded[offset - base] != value}
        seen.update(offset for offset in wanted if base <= offset < base + len(decoded))
        if selected:
            _, origins = decode_origins(block, raw)
            edits = {}
            for offset, value in selected.items():
                origin = origins[offset]
                require(origin not in edits or edits[origin] == value, 'Conflicting literal edits')
                edits[origin] = value
            collateral = [base + i for i, origin in enumerate(origins)
                          if origin in edits and decoded[i] != edits[origin] and i not in selected]
            patched = bytearray(block)
            for origin, value in edits.items():
                patched[origin] = value
            after = bytes(patched) if raw else lz4.block.decompress(patched, uncompressed_size=65536)
            expected = bytearray(decoded)
            for offset, value in selected.items():
                expected[offset] = value
            require(bool(collateral) == (after != expected), 'Collateral check disagrees with library')
            results.append({'decoded_block_offset': hex(base),
                            'compressed_edits': {hex(cursor + k): v for k, v in edits.items()},
                            'collateral_offsets': [hex(x) for x in collateral],
                            'exact_edit': after == expected})
        cursor += size
        base += len(decoded)
    require(seen == set(wanted), 'Patch outside decoded image')
    return results


def main():
    original = (ROOT / 'Insta360AcePro2FW.bin').read_bytes()
    require(sha(original) == SOURCES['Insta360AcePro2FW.bin'], 'Original image changed')
    frame = unpack_package(original)['parts'][0]['payload']
    for name, patches in {
        'compare_self_gate': {0x319ea0: bytes.fromhex('df02166b')},
        'always_compare_factory_gate': {0x319ea4: bytes.fromhex('00e8427a')},
        'preserve_narrow_halfword': {0x3b1540: bytes.fromhex('7f6e0079')},
    }.items():
        print(json.dumps({'proposal': name, 'blocks': inspect_edits(frame, patches)}))


if __name__ == '__main__':
    main()
