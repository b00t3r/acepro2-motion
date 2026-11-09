"""Stage marker-only Trial K after checking identity and its offline tests."""
import json
import os
import plistlib
import subprocess
import sys

import stage_colour_trial as staging
from build_usb_name_candidate import ROOT
from stage_motion_trial import VOLUME, UUID, require, checksum

EXPECTED = '6d89521e63b2bdff9b161a67e804df6389202a3950c6483756c0bb3a97a2f559'
OUT = ROOT/'builds/offline-marker-diagnostic'
DEST = OUT/'Insta360AcePro2_v2.0.51_Marker-Only-Diagnostic_Trial-K.bin'


def main():
    for pattern in ('test_marker_only_diagnostic.py', 'test_fullsensor_marker_hook.py',
                    'test_fullsensor_marker.py'):
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern], check=True)
    require(checksum(DEST) == EXPECTED, 'Diagnostic firmware hash mismatch')
    info = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME)
            and info.get('Writable') and not info.get('Internal') and info.get('FilesystemType') == 'exfat',
            'Unexpected card')
    tree = plistlib.loads(subprocess.check_output(['ioreg','-p','IOService','-a','-l','-r','-c','IOUSBHostDevice']))
    def names(node):
        result = [node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren', []): result.extend(names(child))
        return result
    matches = [n for n in tree if n.get('idVendor') == 0x070a and n.get('idProduct') == 0x4026
               and info['DeviceIdentifier'] in names(n)]
    require(len(matches) == 1 and matches[0].get('USB Product Name') == 'Insta360 Ace Pro X',
            'Expected the camera running Trial X')
    require(not (VOLUME/'Insta360AcePro2FW.bin').exists() and
            not (VOLUME/'Insta360AcePro2FW.bin.copying').exists(), 'Update already present')
    marker = VOLUME/'FULLSENSOR.ENABLE'
    require(not marker.is_symlink(), 'Unexpected marker symlink')
    if marker.exists():
        require(marker.is_file(), 'Existing marker is not a file')
    else:
        with marker.open('xb') as out:
            out.write(b'Marker-only diagnostic; no high-resolution mode enabled.\n')
            out.flush()
            os.fsync(out.fileno())
    require(marker.is_file(), 'Marker creation failed')
    report_path = OUT/'build_report.json'
    report = json.loads(report_path.read_text())
    report.update(regression_tests_passed=6, package_integrity_verified=True,
                  marker_path=str(marker), fullsensor_enabled=False)
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    staging.OUT, staging.DEST, staging.EXPECTED = OUT, DEST, EXPECTED
    staging.main(required_tests=6, previous_usb_name='Insta360 Ace Pro X',
                 next_usb_name='Insta360 Ace Pro K', trial='K (marker-only diagnostic)')


if __name__ == '__main__': main()
