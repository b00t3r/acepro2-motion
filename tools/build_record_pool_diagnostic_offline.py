"""Add a marker-gated pre-teardown pool query to Q3, for offline testing only."""
import json
import subprocess
from build_background_prototype import link_regions
from build_raw_8k_diagnostic_offline import build as build_q3, OUT as Q3_OUT
from livephoto_geometry_patch import branch
from livephoto_harness import BASE, ROOT

HOOK = 0x306464
STUB, END, STATE = 0x2552ec0, 0x2552fe0, 0x2552fe0
OUT = ROOT / 'builds/offline-record-pool-diagnostic'


def build():
    build_q3()
    OUT.mkdir(parents=True, exist_ok=True)
    obj = OUT / 'record_pool_diagnostic.o'
    subprocess.run(['clang', '-target', 'aarch64-none-elf', '-c',
        str(ROOT / 'tools/record_pool_diagnostic.S'), '-o', str(obj)], check=True)
    blobs, symbols, _ = link_regions([(STUB, END, [obj])],
        {'raw_diag_state': STATE, 'native_get_pool_info': 0xdca900,
         'record_stop_continue': HOOK + 4})
    data = bytearray((Q3_OUT / 'main_threadx_OFFLINE_ONLY.bin').read_bytes())
    if data[HOOK-BASE:HOOK-BASE+4] != bytes.fromhex('02778152'):
        raise ValueError('Unexpected pre-stop instruction')
    if any(data[STUB-BASE:END-BASE]):
        raise ValueError('Diagnostic region is occupied')
    data[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, symbols['record_pool_diagnostic'])
    data[STUB-BASE:STUB-BASE+len(blobs[0])] = blobs[0]
    path = OUT / 'main_threadx_OFFLINE_ONLY.bin'
    path.write_bytes(data)
    report = dict(hook=hex(HOOK), diagnostic_state=hex(STATE), stub=hex(STUB),
        measurement='After the stop request, before the native stream-stop operation.',
        limitations=['Offline image only: not a flashable firmware package.',
          'Marker is the existing Q3 state, not a direct 8K-mode check.',
          'The real memory query, task stack, timing and pool stability have not been tested on hardware.',
          'The result is taken after a stop request, not at an arbitrary time during recording.'])
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
