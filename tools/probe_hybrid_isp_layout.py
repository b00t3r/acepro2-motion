"""Inspect a possible full-resolution still tuning alongside Live Photo video.

The composed bytes exist only in this process. No selector is patched and no
ISP processing, DSP behavior, or photo quality is emulated or established.
"""
import json
import struct

from livephoto_harness import BASE, ROOT, image

WORD = 8
SECTION_WORDS = 27
LIVE_PREVIEW = 1
LIVE_HDS = 28
LIVE_STILL = 55
FULL_STILL = 28
ROOTS = {'jpeg': (0x39dbf28, 0x39d8908),
         'pureshot': (0x39e38f0, 0x39e02d0)}


def section(data, root, word):
    off = root - BASE + word * WORD
    raw = data[off:off + SECTION_WORDS * WORD]
    words = struct.unpack('<27Q', raw)
    if words[0] != 0xcafe:
        raise ValueError('Expected native tuning section marker')
    name = data[words[1]-BASE:words[1]-BASE+120].split(b'\0')[0].decode('ascii')
    return raw, name, words[2]


def prototype(kind):
    data = image()
    live, full = ROOTS[kind]
    preview, preview_name, _ = section(data, live, LIVE_PREVIEW)
    hds, hds_name, _ = section(data, live, LIVE_HDS)
    old_still, old_name, old_flags = section(data, live, LIVE_STILL)
    new_still, new_name, new_flags = section(data, full, FULL_STILL)
    if old_flags != new_flags:
        raise ValueError('The still sections have different native flags')
    root_name = data[live - BASE:live - BASE + WORD]
    # Native sections are consecutive; a null word terminates each table.
    hybrid = root_name + preview + hds + new_still + bytes(WORD)
    return hybrid, dict(kind=kind, original_preview=preview_name, original_hds=hds_name,
                        original_still=old_name, proposed_still=new_name,
                        matching_section_flags=hex(new_flags),
                        original_still_bytes=len(old_still),
                        preview_and_hds_byte_exact=True,
                        selector_patched=False, hardware_executed=False,
                        valid_processing_not_established=True)


if __name__ == '__main__':
    rows = [prototype(k)[1] for k in ROOTS]
    output = ROOT / 'analysis/motion-resolution-audit/hybrid-isp-layout.json'
    output.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows, indent=2))
