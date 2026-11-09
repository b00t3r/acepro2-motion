"""Enable existing intermediate-still diagnostics on the identified Trial T card."""
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path
from stage_motion_trial import VOLUME,UUID,require,ROOT

MARKERS=('INS_STILL_CAP_DEBUG_ITUNER','INS_STILL_CAP_DEBUG_R2Y','INS_STILL_CAP_DEBUG_YUV')


def main():
    info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(info.get('VolumeUUID')==UUID and info.get('MountPoint')==str(VOLUME),'Unexpected card')
    require(info.get('Writable') and not info.get('Internal') and info.get('FilesystemType')=='exfat','Expected writable external exFAT card')
    tree=plistlib.loads(subprocess.check_output(['ioreg','-p','IOService','-a','-l','-r','-c','IOUSBHostDevice']))
    def devices(node):
        names=[node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren',[]):
            names.extend(devices(child))
        return names
    matches=[n for n in tree if n.get('idVendor')==0x070a and n.get('idProduct')==0x4026 and info['DeviceIdentifier'] in devices(n)]
    require(len(matches)==1 and matches[0].get('USB Product Name')=='Insta360 Ace Pro T','Expected identified Trial T camera')
    require(shutil.disk_usage(VOLUME).free>512*1024*1024,'Need space for diagnostic snapshots')
    require(not (VOLUME/'Insta360AcePro2FW.bin').exists(),'An update is staged; stop before diagnostic test')
    for path in VOLUME.glob('INS_STILL_CAP_DEBUG*'):
        require(path.name in MARKERS and path.is_file() and path.stat().st_size==0,'Unexpected existing diagnostic control')
    for name in MARKERS:
        path=VOLUME/name
        if not path.exists():
            with path.open('xb') as out:
                out.flush()
                os.fsync(out.fileno())
        require(path.read_bytes()==b'','Marker readback mismatch')
    subprocess.run(['sync'],check=True)
    record=dict(usb_product='Insta360 Ace Pro T',volume_uuid=UUID,markers=list(MARKERS),
                firmware_changed=False,status='Native diagnostic markers installed and read back',
                hardware_dump_generation_verified=False,
                next_test='Two ordinary JPEG Live Photos at 2x, same scene, waiting for save completion; then export logs')
    out=ROOT/'analysis/green-trial-t/debug-marker-status.json'
    out.write_text(json.dumps(record,indent=2)+'\n')
    current=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(current.get('VolumeUUID')==UUID and current['ParentWholeDisk']==info['ParentWholeDisk'],'Card changed before eject')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record.update(ejected=True,status='Native diagnostic markers installed, read back and safely ejected')
    out.write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'])


if __name__=='__main__':
    main()
