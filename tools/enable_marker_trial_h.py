"""Enable the experimental full-sensor diagnostic on the verified camera."""
import json
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
    require(len(matches) == 1 and matches[0].get('USB Product Name') == 'Insta360 Ace Pro H', 'Expected Trial H')
    src, dst = VOLUME/'FULLSENSOR.DISABLED', VOLUME/'FULLSENSOR.ENABLE'
    require(src.is_file() and not src.is_symlink() and not dst.exists(), 'Unexpected marker state')
    require(src.read_bytes() == b'Marker-only diagnostic; no high-resolution mode enabled.\n',
            'Marker contents changed')
    src.rename(dst)
    subprocess.run(['sync'], check=True)
    require(dst.is_file() and not src.exists(), 'Marker rename not verified')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record = dict(status='Full-sensor marker enabled; camera ejected; awaiting hardware test',
                  marker='FULLSENSOR.ENABLE', usb_marker='Insta360 Ace Pro H',
                  higher_resolution_hardware_verified=False)
    (ROOT/'analysis/trial-h-fullsensor-hardware/marker-enabled.json').write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'])


if __name__=='__main__': main()
