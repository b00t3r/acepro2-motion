"""Back up the known camera card, then restore two unambiguous album test groups.

Never formats the disk or changes partitions. macOS-managed cache directories
are left alone; all other existing card content is backed up and verified
before removal. No firmware update is staged.
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import argparse
from pathlib import Path

from stage_motion_trial import checksum, require, VOLUME, UUID

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT/'analysis/colour-trial-n-hardware'
OUT = ROOT/'analysis/clean-album-test'
BACKUP = ROOT/'analysis/sd-card-backup-before-clean-album-test'
OS_CACHES = {'.fseventsd', '.Spotlight-V100', '.Trashes', '.TemporaryItems'}
STEMS = ('LIV_20261029_143128_938', 'LIV_20261029_143134_939')


def card_info():
    info = plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
    require(info.get('VolumeUUID') == UUID and info.get('MountPoint') == str(VOLUME), 'Unexpected card')
    require(info.get('Writable') and not info.get('Internal') and info.get('FilesystemType') == 'exfat',
            'Expected writable external exFAT card')
    return info


def inventory():
    result = []
    for top in sorted(VOLUME.iterdir()):
        if top.name in OS_CACHES:
            continue
        paths = [top] if top.is_file() else sorted(top.rglob('*'))
        require(not top.is_symlink(), 'Unexpected symlink on card')
        for p in paths:
            require(not p.is_symlink(), 'Unexpected symlink on card')
            if p.is_file():
                result.append({'path':str(p.relative_to(VOLUME)), 'bytes':p.stat().st_size})
    return result


def ignore_vanished_companion(function, path, error):
    # macOS may remove ._ sidecars when their corresponding media is unlinked.
    if not isinstance(error[1], FileNotFoundError):
        raise error[1]


def verify_and_eject(info, wanted, record, status, rows):
    subprocess.run(['sync'],check=True)
    for row in wanted:
        require(checksum(VOLUME/row['path']) == row['sha256'], 'Final restored file read-back failed')
    actual = []
    companions = []
    for row in inventory():
        p = Path(row['path'])
        if p.name.startswith('._') and (VOLUME/p.with_name(p.name[2:])).exists():
            companions.append(row['path'])
        else:
            actual.append(row)
    require(actual == sorted([{'path':r['path'],'bytes':r['bytes']} for r in wanted],key=lambda r:r['path']),
            'Unexpected non-companion files after restore')
    current = card_info()
    require(current['ParentWholeDisk'] == info['ParentWholeDisk'], 'Card identity changed before eject')
    record.update(status='Two test groups restored and verified; eject pending',
                  backup_files=len(rows), backup_bytes=sum(r['bytes'] for r in rows),
                  macos_generated_companion_files=companions)
    status.write_text(json.dumps(record,indent=2)+'\n')
    subprocess.run(['diskutil','eject',info['ParentWholeDisk']],check=True)
    record.update(status='Two test groups restored, hash-verified and safely ejected',ejected=True)
    status.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ('status','backup','backup_files','backup_bytes')},indent=2))


def main(resume=False, verify_restore=False):
    manifest = {row['name']:row for row in json.loads((BASELINE/'files.json').read_text())}
    info = card_info()
    tree = plistlib.loads(subprocess.check_output(
        ['ioreg','-p','IOService','-a','-l','-r','-c','IOUSBHostDevice']))
    def names(node):
        result = [node['BSD Name']] if 'BSD Name' in node else []
        for child in node.get('IORegistryEntryChildren', []):
            result.extend(names(child))
        return result
    cameras = [n for n in tree if n.get('idVendor') == 0x070a and n.get('idProduct') == 0x4026
               and info['DeviceIdentifier'] in names(n)]
    require(len(cameras) == 1 and cameras[0].get('USB Product Name') == 'Insta360 Ace Pro N',
            'Expected the camera running Trial N')
    if verify_restore:
        record = json.loads((OUT/'staging_status.json').read_text())
        require(record['volume_uuid'] == UUID and record['device'] == info['DeviceIdentifier'],
                'Restoration record does not match the card')
        rows = json.loads((OUT/'backup_manifest.json').read_text())
        for row in rows:
            require(checksum(BACKUP/row['path']) == row['sha256'], 'Existing backup verification failed')
        return verify_and_eject(info,record['restore_files'],record,OUT/'staging_status.json',rows)
    require(resume or not BACKUP.exists(), 'Backup directory already exists; inspect before retrying')
    rows = (json.loads((OUT/'backup_manifest.json').read_text()) if resume else inventory())
    require(rows, 'Card inventory is empty')
    require(shutil.disk_usage(ROOT).free > sum(r['bytes'] for r in rows)+256*1024*1024,
            'Insufficient local backup space')
    OUT.mkdir(exist_ok=True)
    restore = OUT/'restore/DCIM/Camera01'
    restore.mkdir(parents=True,exist_ok=True)
    wanted = []
    for stem in STEMS:
        for suffix in ('.jpg','.lrv','.mp4'):
            source_name = stem+('.lrv' if stem == STEMS[1] and suffix == '.mp4' else suffix)
            src = BASELINE/source_name
            expected = manifest[source_name]['sha256']
            require(checksum(src) == expected, 'Local baseline changed')
            dest = restore/(stem+suffix)
            shutil.copyfile(src,dest)
            require(checksum(dest) == expected, 'Local restore copy failed')
            wanted.append({'path':str(dest.relative_to(OUT/'restore')), 'bytes':dest.stat().st_size,
                           'sha256':expected})
    record = dict(status=('Verifying existing backup before resuming restoration' if resume
                          else 'Backing up card; no removal performed'), volume_uuid=UUID,
                  device=info['DeviceIdentifier'], backup=str(BACKUP), restore_files=wanted,
                  firmware_changed=False, ejected=False)
    status = OUT/'staging_status.json'
    status.write_text(json.dumps(record,indent=2)+'\n')
    BACKUP.mkdir(exist_ok=resume)
    for row in rows:
        src = VOLUME/row['path']
        dst = BACKUP/row['path']
        dst.parent.mkdir(parents=True,exist_ok=True)
        if resume:
            require(checksum(dst) == row['sha256'], 'Existing backup verification failed')
        else:
            before = checksum(src)
            shutil.copyfile(src,dst)
            require(checksum(dst) == before and checksum(src) == before, 'Backup verification failed')
            row['sha256'] = before
    if resume:
        previous = {r['path']:r for r in rows}
        for row in inventory():
            require(row['path'] in previous and checksum(VOLUME/row['path']) == previous[row['path']]['sha256'],
                    'Card contains a new or changed file; refusing to remove it')
    else:
        require(inventory() == [{k:r[k] for k in ('path','bytes')} for r in rows],
                'Card contents changed during backup')
    (OUT/'backup_manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
    current = card_info()
    require(current['ParentWholeDisk'] == info['ParentWholeDisk'], 'Card identity changed')
    for row in (inventory() if resume else rows):
        if resume:
            row['sha256'] = previous[row['path']]['sha256']
        require(checksum(VOLUME/row['path']) == row['sha256'], 'Card file changed before removal')
    record['status'] = 'All user/camera files backed up and hash-verified; restoring test set'
    status.write_text(json.dumps(record,indent=2)+'\n')
    for top in VOLUME.iterdir():
        if top.name in OS_CACHES:
            continue
        if top.is_dir():
            shutil.rmtree(top,onerror=ignore_vanished_companion)
        else:
            top.unlink(missing_ok=True)
    folder = VOLUME/'DCIM/Camera01'
    folder.mkdir(parents=True)
    for row in wanted:
        src = OUT/'restore'/row['path']
        dst = VOLUME/row['path']
        with src.open('rb') as inp, dst.open('xb') as out:
            shutil.copyfileobj(inp,out,length=1024*1024)
            out.flush()
            os.fsync(out.fileno())
        require(checksum(dst) == row['sha256'], 'Restored file verification failed')
    verify_and_eject(info,wanted,record,status,rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--verify-restored', action='store_true')
    args = parser.parse_args()
    main(args.resume,args.verify_restored)
