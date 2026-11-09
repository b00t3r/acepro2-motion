"""Reversible album probe on one hash-verified Trial N test capture."""
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from stage_motion_trial import checksum, require, VOLUME, UUID

ROOT = Path(__file__).resolve().parents[1]
STEM = 'LIV_20261029_143134_939'
BASELINE = ROOT/'analysis/colour-trial-n-hardware'
OUT = ROOT/'analysis/lrv-album-probe'


def main():
    manifest = {row['name']: row for row in json.loads((BASELINE/'files.json').read_text())}
    originals = {suffix: BASELINE/(STEM+suffix) for suffix in ('.jpg', '.mp4', '.lrv', '.MP.jpg')}
    for suffix, path in originals.items():
        require(checksum(path) == manifest[path.name]['sha256'], 'Local baseline changed: '+suffix)
    info = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME), 'Unexpected card')
    require(info.get('Writable') and not info.get('Internal') and info.get('FilesystemType') == 'exfat',
            'Expected writable external exFAT card')
    tree = plistlib.loads(subprocess.check_output(
        ['ioreg','-p','IOService','-a','-l','-r','-c','IOUSBHostDevice']))
    def device_names(node):
        names = [node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren', []):
            names.extend(device_names(child))
        return names
    cameras = [node for node in tree if node.get('idVendor') == 0x070a and node.get('idProduct') == 0x4026
               and info['DeviceIdentifier'] in device_names(node)]
    require(len(cameras) == 1 and cameras[0].get('USB Product Name') == 'Insta360 Ace Pro N',
            'Expected the camera running Trial N')
    folder = VOLUME/'DCIM/Camera01'
    for suffix, path in originals.items():
        require(checksum(folder/path.name) == manifest[path.name]['sha256'], 'Camera capture changed: '+suffix)
    backup = VOLUME/'CODEX_BACKUP'/(STEM+'.mp4')
    temp = folder/(STEM+'.mp4.copying')
    final = folder/(STEM+'.mp4')
    require(not backup.exists() and not temp.exists(), 'A previous album probe is already present')
    require(shutil.disk_usage(VOLUME).free > originals['.lrv'].stat().st_size+1024*1024, 'Insufficient space')
    OUT.mkdir(exist_ok=True)
    record = dict(capture=STEM, status='Preparing reversible album probe', volume_uuid=UUID,
                  device=info['DeviceIdentifier'], original_main_sha256=manifest[final.name]['sha256'],
                  replacement_sha256=manifest[STEM+'.lrv']['sha256'],
                  original_main_backup_on_card=str(backup), original_main_backup_local=str(originals['.mp4']),
                  firmware_changed=False, camera_album_playback_verified=False, ejected=False)
    record_path = OUT/'staging_status.json'
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    with originals['.lrv'].open('rb') as inp, temp.open('xb') as out:
        shutil.copyfileobj(inp,out,length=1024*1024)
        out.flush()
        os.fsync(out.fileno())
    require(checksum(temp) == record['replacement_sha256'], 'Temporary replacement verification failed')
    backup.parent.mkdir(exist_ok=True)
    final.rename(backup)
    try:
        temp.rename(final)
    except Exception:
        backup.rename(final)
        raise
    subprocess.run(['sync'],check=True)
    require(checksum(final) == record['replacement_sha256'], 'Final replacement read-back failed')
    require(checksum(backup) == record['original_main_sha256'], 'Original backup read-back failed')
    for suffix in ('.jpg','.lrv','.MP.jpg'):
        require(checksum(folder/(STEM+suffix)) == manifest[STEM+suffix]['sha256'], 'Other media changed')
    record.update(status='LRV installed as main MP4; both copies verified; original preserved; eject pending',
                  main_bytes_before=originals['.mp4'].stat().st_size, main_bytes_after=final.stat().st_size)
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    current = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(current.get('VolumeUUID') == UUID and current['ParentWholeDisk'] == info['ParentWholeDisk'],
            'Card identity changed')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record.update(status='Reversible LRV-as-main-MP4 album probe staged and safely ejected',ejected=True)
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__ == '__main__':
    main()
