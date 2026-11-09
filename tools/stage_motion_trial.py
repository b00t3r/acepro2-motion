"""Stage only the validated Trial M on the previously identified camera card."""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'builds/offline-motion-photo'
SOURCE = BUILD / 'Insta360AcePro2_v2.0.51_LivePhoto-2x_Extra-MotionPhoto_Trial-M.bin'
EXPECTED = '040fd19f232e3ab05b25bd4c03fa8fbd0c2c028c30a5d15b45aa637910d35d22'
VOLUME = Path('/Volumes/Untitled')
UUID = '3A8C3713-C262-3DB7-8BEC-604865B64393'


def checksum(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(checksum(SOURCE) == EXPECTED, 'Candidate checksum changed')
    report = json.loads((BUILD/'build_report.json').read_text())
    require(report['regression_tests_passed'] == 84, 'Required tests not recorded')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME), 'Unexpected card')
    require(info.get('Writable') and not info.get('Internal'), 'Card is not writable external storage')
    require(info.get('FilesystemType') == 'exfat', 'Unexpected filesystem')
    tree = plistlib.loads(subprocess.check_output(
        ['ioreg', '-p', 'IOService', '-a', '-l', '-r', '-c', 'IOUSBHostDevice']))
    matches = []
    for node in tree:
        if node.get('idVendor') != 0x070a or node.get('idProduct') != 0x4026:
            continue
        devices = []
        def walk(n):
            if 'BSD Name' in n:
                devices.append(n['BSD Name'])
            for child in n.get('IORegistryEntryChildren', []):
                walk(child)
        walk(node)
        if info['DeviceIdentifier'] in devices:
            matches.append(node)
    require(len(matches) == 1 and matches[0].get('USB Product Name') == 'Insta360 Ace Pro V',
            'Expected the camera running the working Trial V')
    dest = VOLUME / 'Insta360AcePro2FW.bin'
    temp = VOLUME / 'Insta360AcePro2FW.bin.copying'
    require(not dest.exists() and not temp.exists(), 'Update file already present; refusing overwrite')
    require(shutil.disk_usage(VOLUME).free > SOURCE.stat().st_size + 16*1024*1024, 'Not enough free space')
    record = {'status':'Copying Trial M', 'candidate_sha256':EXPECTED,
              'camera_usb_name_before_update':'Insta360 Ace Pro V',
              'expected_usb_name_after_update':'Insta360 Ace Pro M', 'volume_uuid':UUID,
              'device':info['DeviceIdentifier'], 'whole_disk':info['ParentWholeDisk'],
              'hardware_installation_verified':False, 'ejected':False}
    record_path = BUILD/'staging_status.json'
    record_path.write_text(json.dumps(record, indent=2)+'\n')
    with SOURCE.open('rb') as inp, temp.open('xb') as out:
        shutil.copyfileobj(inp, out, length=1024*1024)
        out.flush()
        os.fsync(out.fileno())
    require(checksum(temp) == EXPECTED, 'Temporary copy read-back mismatch')
    require(not dest.exists(), 'Destination appeared while copying')
    temp.rename(dest)
    subprocess.run(['sync'], check=True)
    require(checksum(dest) == EXPECTED, 'Final copy read-back mismatch')
    record.update(status='Staged and full read-back verified; eject pending', readback_sha256=EXPECTED)
    record_path.write_text(json.dumps(record, indent=2)+'\n')
    current = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(VOLUME)]))
    require(current.get('VolumeUUID') == UUID and current['ParentWholeDisk'] == info['ParentWholeDisk'],
            'Card identity changed before eject')
    result = subprocess.run(['diskutil', 'eject', info['ParentWholeDisk']], capture_output=True, text=True)
    if result.returncode:
        print(result.stdout + result.stderr)
        raise RuntimeError('Copy verified, but safe eject failed; inspect staging_status.json')
    record.update(status='Trial M staged, full read-back verified and safely ejected; awaiting camera update',
                  ejected=True)
    record_path.write_text(json.dumps(record, indent=2)+'\n')
    report['status'] = record['status']
    (BUILD/'build_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(record['status'])


if __name__ == '__main__':
    main()
