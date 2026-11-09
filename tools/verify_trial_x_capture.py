"""Verify copied Trial X captures and recorded allocations; never alter the card."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'analysis/trial-x-memory-hardware'


def strip_xmp(data):
    pos = 2
    while data[pos:pos + 2] in (b'\xff\xe0', b'\xff\xe1'):
        size = int.from_bytes(data[pos + 2:pos + 4], 'big') + 2
        if data[pos + 4:pos + 33] == b'http://ns.adobe.com/xap/1.0/\x00':
            return data[:pos] + data[pos + size:]
        pos += size
    raise ValueError('Expected leading XMP segment not found')


def main():
    # The firmware's log rotation divides capture 974 across these two files.
    logs = FOLDER / 'logs/decoded'
    text = ''.join((logs / name).read_text(errors='replace') for name in
                   ('20261030_02.txt', '20261030_03.log.txt'))
    (FOLDER / 'combined-capture-log.txt').write_text(text)
    captures = []
    for path in sorted((FOLDER / 'captures').glob('*.MP.jpg')):
        stem = path.name[:-7]
        original = path.with_name(stem + '.jpg').read_bytes()
        lrv = path.with_name(stem + '.lrv').read_bytes()
        combined = path.read_bytes()
        timestamp = int(re.search(rb'MotionPhotoPresentationTimestampUs="(\d+)"', combined)[1])
        result = dict(stem=stem, original_jpeg_byte_exact=
                      strip_xmp(combined[:-len(lrv)]) == original,
                      embedded_lrv_byte_exact=combined.endswith(lrv),
                      timestamp_us=timestamp)
        assert result['original_jpeg_byte_exact'] and result['embedded_lrv_byte_exact']
        captures.append(result)
    pool = re.findall(r'StillBufTotalBase 0x([0-9A-Fa-f]+), StillBufTotalSize 0x([0-9A-Fa-f]+)', text)
    base, size = (int(value, 16) for value in pool[-1])
    video = re.findall(r'Video\[0\] Enc Para W:3840 H:2880[^\n]*BufferSize (\d+)', text)
    assert int(video[-1]) == 268369920
    assert (base, size) == (0xe43b6e00, 427069952)
    report = dict(usb_identity='Insta360 Ace Pro X',
                  usb_evidence='usb-identity.json',
                  still_pool_base=hex(base), still_pool_bytes=size,
                  previous_w_still_pool_bytes=170824192,
                  still_pool_increase_bytes=size - 170824192,
                  video_buffer_bytes=int(video[-1]), captures=captures,
                  higher_resolution_enabled=False,
                  visual_check='Both copied stills have normal colours; 2x image is cropped as expected.',
                  limits=['Still resolution remains 4096x3072.',
                          'No new ordinary video capture identified after installation.',
                          'File structure checks do not establish phone or camera motion playback.',
                          'Full-resolution sensor, DSP and ISP changes remain unvalidated.'])
    (FOLDER / 'findings.json').write_text(json.dumps(report, indent=2) + '\n')
    for filename in ('build_report.json', 'staging_status.json'):
        path = ROOT / 'builds/offline-highres-memory' / filename
        status = json.loads(path.read_text())
        status.update(status='Trial X installation and 4:3 Live Photo memory change verified on hardware',
                      hardware_installation_verified=True,
                      hardware_evidence=str((FOLDER / 'findings.json').relative_to(ROOT)))
        if filename == 'build_report.json':
            status['hardware_verified'] = True
            status['hardware_verified_scope'] = 'USB X, 256 MiB usable video buffer, enlarged still pool, normal-colour 1x/2x stills, byte-exact JPEG/LRV Motion Photo packaging. Higher resolution and ordinary video fallback not hardware validated.'
        path.write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
