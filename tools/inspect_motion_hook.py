"""Read-only stock image disassembly and string references for capture finalization."""
import argparse
import json
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from inspect_firmware import find_refs, strings

ROOT = Path(__file__).resolve().parent.parent
BASE = 0x50000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--find', nargs='+')
    parser.add_argument('--range', nargs=2, type=lambda x: int(x, 0))
    args = parser.parse_args()
    data = (ROOT / 'analysis/extracted/main_threadx.bin').read_bytes()
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    if args.find:
        targets = {text: offset for offset, text in strings(data)
                   if any(needle.lower() in text.lower() for needle in args.find)}
        refs = find_refs(data, BASE, targets, lookahead=8)
        print(json.dumps({'strings': {k: hex(BASE+v) for k, v in targets.items()},
                          'refs': [{'label': r['label'], 'address': hex(r['address'])}
                                   for r in refs]}, indent=2))
    if args.range:
        start, end = args.range
        for i in md.disasm(data[start-BASE:end-BASE], start):
            print(f'{i.address:08x} {i.bytes.hex():8s} {i.mnemonic:8s} {i.op_str}')


if __name__ == '__main__':
    main()
