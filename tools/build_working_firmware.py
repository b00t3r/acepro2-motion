#!/usr/bin/env python3
"""Rebuild the tested T3 firmware from the two original update files.

Creates and overwrites intermediate files under builds/ and analysis/.
This does not access the camera or install the resulting firmware.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUTS = {
    'Insta360AcePro2FW.bin': '9b5b98818a05b7e9d95dad00990ad0c8e978aa59de80867d6fc59010d5cb7094',
    'Insta360AcePro2FW.bin.old.bin': '6ad878a7e756ea0e68627ecd2bb016dd4f5405b625e795dc6b7ab9355327a9aa',
}
STEPS = [
    ('inspect_firmware.py',),
    ('build_livephoto_candidate.py', '--both-ui-states', '--pixel-crop'),
    ('build_motion_candidate.py',),
    ('build_colour_candidate.py',),
    ('build_small_main_candidate.py',),
    ('build_gallery_bitrate_candidate.py',),
    ('build_fast_copy_candidate.py',),
    ('build_live_capmode_candidate.py',),
    ('build_live_isp_candidate.py',),
    ('build_background_candidate.py',),
    ('build_highres_memory_candidate.py',),
    ('build_record_pool_diagnostic_candidate.py',),
    ('build_gallery_motion_candidate.py',),
]
OUTPUT = ROOT / 'builds/offline-gallery-motion/Insta360AcePro2_Gallery-Motion_Builder_Trial-T3.bin'
EXPECTED = '9bd908d79770725228e3c96627ee5281e455772c0dcc4b3addaa7b83a1f4e877'

def digest(path):
    with path.open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    if not shutil.which('clang'):
        sys.exit('Error: clang is required to build AArch64 code.')
    for name, expected in INPUTS.items():
        path = ROOT / name
        if not path.is_file():
            sys.exit(f'Error: missing original firmware {path}')
        if digest(path) != expected:
            sys.exit(f'Error: {name} does not match the required original firmware.')
    (ROOT / 'builds').mkdir(exist_ok=True)
    (ROOT / 'analysis').mkdir(exist_ok=True)
    for script, *args in STEPS:
        print(f'\nBuilding: {script}', flush=True)
        subprocess.run([sys.executable, str(ROOT / 'tools' / script), *args], cwd=ROOT, check=True)
    if digest(OUTPUT) != EXPECTED:
        sys.exit('Error: output differs from the tested T3 build. Do not install it.')
    print(f'\nBuilt and verified: {OUTPUT}')
    print('Nothing was installed on the camera.')

if __name__ == '__main__':
    main()
