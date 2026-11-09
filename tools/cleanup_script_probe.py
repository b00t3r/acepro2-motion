#!/usr/bin/env python3
"""Record the probe result and remove only the verified probe artifacts."""
import json
import plistlib
import subprocess
from pathlib import Path

from install_script_probe import ROOT, VOLUME, MARKER, EXPECTED, require


def main():
    tree = plistlib.loads(subprocess.check_output([
        'ioreg', '-a', '-l', '-r', '-n', 'Insta360 Ace Pro 2', '-p', 'IOService']))
    require(len(tree) == 1, 'Expected exactly one Ace Pro 2')
    camera = tree[0]
    require(camera.get('idVendor') == 0x070a and camera.get('idProduct') == 0x4026,
            'Unexpected USB identity')
    devices = []

    def walk(node):
        if 'BSD Name' in node:
            devices.append(node['BSD Name'])
        for child in node.get('IORegistryEntryChildren', []):
            walk(child)

    walk(camera)
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(VOLUME)]))
    require(info.get('DeviceIdentifier') in devices, 'Volume does not belong to the camera')
    script = VOLUME / 'svc_auto_run.ash'
    require(script.is_file() and not script.is_symlink(), 'Expected regular probe file')
    require(script.read_bytes() == EXPECTED.replace(b'\n', b'\r\n'), 'Probe contents changed; refusing removal')
    marker = VOLUME / MARKER
    appeared = marker.exists()
    if appeared:
        require(marker.is_dir() and not marker.is_symlink() and not any(marker.iterdir()),
                'Marker is not an empty directory; refusing removal')
    sidecar = VOLUME / '._svc_auto_run.ash'
    if sidecar.exists():
        require(sidecar.is_file() and not sidecar.is_symlink(), 'Unexpected metadata file type')
        require(sidecar.read_bytes()[:4] == b'\x00\x05\x16\x07', 'Unexpected metadata file format')
    status_path = ROOT / 'analysis/script_probe_status.json'
    record = json.loads(status_path.read_text())
    require(record.get('marker_existed_before') is False, 'Missing negative baseline')
    record.update({'marker_observed_after_reconnect': appeared,
                   'root_entries_after_reconnect': sorted(p.name for p in VOLUME.iterdir()),
                   'status': 'result recorded; cleanup pending',
                   'result': 'marker present: execution observed' if appeared else
                             'marker absent: execution not confirmed'})
    status_path.write_text(json.dumps(record, indent=2) + '\n')
    script.unlink()
    if sidecar.exists():
        sidecar.unlink()
    if appeared:
        marker.rmdir()
    require(not script.exists() and not sidecar.exists() and not marker.exists(), 'Cleanup verification failed')
    record['status'] = 'result recorded; test files removed and absence verified'
    status_path.write_text(json.dumps(record, indent=2) + '\n')
    print(record['result'])
    print('Removed verified probe and its metadata; verified no test files remain on the card.')


if __name__ == '__main__':
    main()
