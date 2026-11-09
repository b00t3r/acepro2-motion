"""Temporarily disable the test marker on the identified Trial L camera."""
import json
import os
import plistlib
import subprocess
from stage_motion_trial import VOLUME, UUID, require
from build_usb_name_candidate import ROOT


def main():
    info = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME), 'Unexpected card')
    tree = plistlib.loads(subprocess.check_output(['ioreg','-p','IOService','-a','-l','-r','-c','IOUSBHostDevice']))
    def names(node):
        result = [node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren', []): result.extend(names(child))
        return result
    matches = [n for n in tree if n.get('idVendor') == 0x070a and n.get('idProduct') == 0x4026
               and info['DeviceIdentifier'] in names(n)]
    require(len(matches) == 1 and matches[0].get('USB Product Name') == 'Insta360 Ace Pro L', 'Expected Trial L')
    src, dst = VOLUME/'FULLSENSOR.ENABLE', VOLUME/'FULLSENSOR.DISABLED'
    require(src.is_file() and not src.is_symlink() and not dst.exists(), 'Unexpected marker state')
    require(src.read_bytes() == b'Marker-only diagnostic; no high-resolution mode enabled.\n',
            'Marker contents changed; refusing to rename')
    src.rename(dst)
    subprocess.run(['sync'], check=True)
    require(dst.is_file() and not src.exists(), 'Marker rename not verified')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record = dict(status='Marker temporarily disabled and card ejected; missing-marker hardware test pending',
                  marker_saved_as='FULLSENSOR.DISABLED', usb_marker='Insta360 Ace Pro L')
    (ROOT/'analysis/trial-l-marker-hardware/marker-disabled.json').write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'])


if __name__ == '__main__': main()
