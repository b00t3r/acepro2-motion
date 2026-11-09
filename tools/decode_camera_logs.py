#!/usr/bin/env python3
"""Decode local exported camera logs using constants from the supplied firmware.

Read-only with respect to the camera and original exports. No network access.
The pinned firmware's logger at VA 0x71d1e0 uses AES-256-CBC, a 16-byte
plaintext prefix, and PKCS#7 padding around a Zstandard frame.
"""
import argparse
import hashlib
import subprocess
from pathlib import Path

import zstandard

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IMAGE_SHA = 'da22a8a0bf105a26192281dc563c7c38a169fcbc1778ee565007143bdc39a02e'


def decode(ciphertext, firmware):
    if not ciphertext or len(ciphertext) % 16:
        raise ValueError('Expected nonempty AES block-aligned ciphertext')
    key = firmware[0x293cfb0 - 0x50000:0x293cfd0 - 0x50000]
    iv = firmware[0x293cf98 - 0x50000:0x293cfa8 - 0x50000]
    result = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc',
                             '-K', key.hex(), '-iv', iv.hex()],
                            input=ciphertext, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('AES decryption or padding verification failed')
    frame = result.stdout[16:]
    if frame[:4] != bytes.fromhex('28b52ffd'):
        raise ValueError('Decoded data lacks the expected Zstandard frame')
    return zstandard.ZstdDecompressor().decompress(frame, max_output_size=16 * 1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    firmware = (ROOT / 'analysis/extracted/main_threadx.bin').read_bytes()
    if hashlib.sha256(firmware).hexdigest() != EXPECTED_IMAGE_SHA:
        raise ValueError('Encryption layout requires the original supplied firmware')
    output = args.directory / 'decoded'
    output.mkdir(exist_ok=True)
    for path in sorted(args.directory.glob('*.crypt')):
        decoded = decode(path.read_bytes(), firmware)
        destination = output / (path.name.removesuffix('.crypt').removesuffix('.zst') + '.txt')
        destination.write_bytes(decoded)
        print(f'{path.name}: decoded {len(decoded)} bytes')


if __name__ == '__main__':
    main()
