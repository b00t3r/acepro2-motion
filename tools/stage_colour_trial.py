"""Stage the hash-pinned, offline-validated Trial N on the known camera card."""
import json
import os
import plistlib
import shutil
import subprocess

from build_colour_candidate import OUT, DEST, sha
from stage_motion_trial import checksum, require, VOLUME, UUID

EXPECTED = 'f8f95352ce7dd0fa58c572552b07378f0a955c8a23571b613ce111941e35382f'


def main(required_tests=95, previous_usb_name='Insta360 Ace Pro M',
         next_usb_name='Insta360 Ace Pro N', trial='N'):
    require(checksum(DEST) == EXPECTED, f'Trial {trial} hash mismatch')
    report = json.loads((OUT/'build_report.json').read_text())
    require(report.get('regression_tests_passed') == required_tests and report.get('package_integrity_verified'),
            'Required offline validation not recorded')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME), 'Unexpected card')
    require(info.get('Writable') and not info.get('Internal') and info.get('FilesystemType') == 'exfat',
            'Expected writable external exFAT card')
    tree = plistlib.loads(subprocess.check_output(
        ['ioreg', '-p', 'IOService', '-a', '-l', '-r', '-c', 'IOUSBHostDevice']))
    matches = []
    def device_names(node):
        names = [node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren', []):
            names.extend(device_names(child))
        return names
    for node in tree:
        if node.get('idVendor') == 0x070a and node.get('idProduct') == 0x4026:
            if info['DeviceIdentifier'] in device_names(node):
                matches.append(node)
    require(len(matches) == 1 and matches[0].get('USB Product Name') == previous_usb_name,
            f'Expected the camera running {previous_usb_name}')
    final = VOLUME/'Insta360AcePro2FW.bin'
    temp = VOLUME/'Insta360AcePro2FW.bin.copying'
    require(not final.exists() and not temp.exists(), 'An update file already exists')
    require(shutil.disk_usage(VOLUME).free > DEST.stat().st_size+16*1024*1024, 'Insufficient space')
    record = dict(status=f'Copying Trial {trial}', candidate_sha256=EXPECTED,
                  expected_usb_name_after_update=next_usb_name,
                  camera_usb_name_before_update=previous_usb_name, volume_uuid=UUID,
                  hardware_installation_verified=False, ejected=False,
                  device=info['DeviceIdentifier'], whole_disk=info['ParentWholeDisk'])
    record_path = OUT/'staging_status.json'
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    with DEST.open('rb') as inp, temp.open('xb') as out:
        shutil.copyfileobj(inp,out,length=1024*1024)
        out.flush()
        os.fsync(out.fileno())
    require(checksum(temp) == EXPECTED, 'Temporary read-back mismatch')
    require(not final.exists(), 'Destination appeared during copy')
    temp.rename(final)
    subprocess.run(['sync'],check=True)
    require(checksum(final) == EXPECTED, 'Final read-back mismatch')
    record.update(status=f'Trial {trial} copied and read-back verified; eject pending',readback_sha256=EXPECTED)
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    current = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(current.get('VolumeUUID') == UUID and current['ParentWholeDisk'] == info['ParentWholeDisk'],
            'Card identity changed before eject')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record.update(status=f'Trial {trial} staged, read-back verified and safely ejected; awaiting update',ejected=True)
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    report['status'] = record['status']
    (OUT/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(record['status'])


if __name__ == '__main__':
    main()
