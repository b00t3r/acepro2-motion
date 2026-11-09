"""Offline experiment: select full-sensor template only for 4:3 Live at 2x.

This creates no update package. It tests configuration control flow, not the
camera's sensor, DSP memory, image quality, video or recovery behavior.
"""
import json
import struct

from livephoto_harness import BASE, ROOT, run_livephoto_config
from livephoto_geometry_patch import branch, instruction

HOOK, STUB = 0x401504, 0x2552c40
ORIGINAL = bytes.fromhex('60160079')  # strh w0, [x19, #0xa]


def payload():
    def bne(offset, target):
        return instruction(0x54000001 | (((target - offset) // 4) & 0x7ffff) << 5)
    return b''.join([
        ORIGINAL,
        instruction(0xa9bf2be9),  # save x9 and x10
        instruction(0xd53b420a),  # save NZCV
        instruction(0x79400e69),  # ldrh w9, [x19, #6]
        instruction(0x7100001f | (227 << 10) | (9 << 5)),
        bne(STUB + 20, STUB + 48),
        instruction(0x79406a69),  # ldrh w9, [x19, #0x34]
        instruction(0x7100053f),  # cmp w9, #1
        bne(STUB + 32, STUB + 48),
        instruction(0x52800009 | (49 << 5)),
        instruction(0x79001269),  # strh w9, [x19, #8]
        instruction(0x79001669),  # strh w9, [x19, #0xa]
        instruction(0xd51b420a),
        instruction(0xa8c12be9),
        branch(STUB + 56, HOOK + 4),
    ])


def experimental_image(original):
    result = bytearray(original)
    if result[HOOK-BASE:HOOK-BASE+4] != ORIGINAL:
        raise ValueError('Unexpected native instruction')
    body = payload()
    if any(result[STUB-BASE:STUB-BASE+len(body)]):
        raise ValueError('Experiment overlaps existing code')
    result[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
    result[STUB-BASE:STUB-BASE+len(body)] = body
    return bytes(result)


def probe():
    original = (ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    modified = experimental_image(original)
    cases = []
    for resource in (21, 226, 227, 228):
        for narrow in (0, 1):
            before = run_livephoto_config(resource, narrow, image_data=original, include_encoding=True)
            after = run_livephoto_config(resource, narrow, image_data=modified, include_encoding=True)
            old, new = bytearray.fromhex(before['packed_config_hex']), bytearray.fromhex(after['packed_config_hex'])
            expected = old[:]
            if (resource, narrow) == (227, 1):
                struct.pack_into('<HH', expected, 8, 49, 49)
            if new != expected:
                raise AssertionError('Unexpected configuration change')
            cases.append(dict(resource=resource, narrow=narrow, original_ids=before['resource_ids'],
                              experimental_ids=after['resource_ids']))
    return dict(cases=cases, firmware_package_created=False, hardware_tested=False,
                limitations=['The hardware reconfiguration path and activation timing are unverified.',
                             'Full-sensor DSP memory requirements, video topology and image quality are unverified.',
                             'The experiment does not set 20 MP output or add a menu item.'])


if __name__ == '__main__':
    result = probe()
    output = ROOT / 'analysis/motion-resolution-audit/guarded-fullsensor-offline.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
