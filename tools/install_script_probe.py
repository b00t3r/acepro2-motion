#!/usr/bin/env python3
"""Install the reviewed directory-only probe on the attached Ace Pro 2 card."""
import json
import os
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOLUME = Path('/Volumes/Untitled')
MARKER = 'AP2P1029'
EXPECTED = b'mkdir C:\\AP2P1029\n'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    source = ROOT / 'probes/svc_auto_run.ash'
    require(source.read_bytes() == EXPECTED, 'Probe differs from reviewed one-line content')
    raw = subprocess.check_output(['ioreg', '-a', '-l', '-r', '-n',
                                   'Insta360 Ace Pro 2', '-p', 'IOService'])
    tree = plistlib.loads(raw)
    require(len(tree) == 1, 'Expected exactly one Ace Pro 2')
    camera = tree[0]
    require(camera.get('idVendor') == 0x070a and camera.get('idProduct') == 0x4026,
            'Unexpected camera USB identity')
    devices = []

    def walk(node):
        if 'BSD Name' in node:
            devices.append(node['BSD Name'])
        for child in node.get('IORegistryEntryChildren', []):
            walk(child)

    walk(camera)
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(VOLUME)]))
    require(info.get('DeviceIdentifier') in devices, 'Mounted card is not attached to the identified camera')
    require(info.get('MountPoint') == str(VOLUME), 'Unexpected mount point')
    require(info.get('FilesystemType', '').lower() == 'exfat', 'Expected exFAT camera card')
    destination = VOLUME / source.name
    require(not destination.exists(), 'A startup script already exists; refusing to replace it')
    require(not (VOLUME / MARKER).exists(), 'Probe marker already exists; cannot distinguish test success')
    baseline = sorted(p.name for p in VOLUME.iterdir())
    # CRLF matches the reader's line-ending handling; no BOM or shell expansion.
    content = EXPECTED.replace(b'\n', b'\r\n')
    with destination.open('xb') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    require(destination.read_bytes() == content, 'Probe read-back mismatch')
    record = {'status': 'installed; awaiting normal camera boot',
              'usb_id': '070a:4026', 'device': info['DeviceIdentifier'],
              'volume': str(VOLUME), 'baseline_root_entries': baseline,
              'probe': source.name, 'command': EXPECTED.decode().strip(),
              'marker': MARKER, 'marker_existed_before': False,
              'firmware_updated': False}
    (ROOT / 'analysis/script_probe_status.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Installed and verified:', destination)
    print('Marker is absent; ready for a normal camera boot after safely ejecting the card.')


if __name__ == '__main__':
    main()
