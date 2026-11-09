"""Back up and remove only the three diagnostic controls created for this test."""
import json
import plistlib
import subprocess
from stage_motion_trial import VOLUME,UUID,ROOT,require
from stage_still_debug_markers import MARKERS

info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(VOLUME)]))
require(info.get('VolumeUUID')==UUID and info.get('MountPoint')==str(VOLUME),'Unexpected card')
out=ROOT/'analysis/still-debug-hardware/disabled-marker-backup'
out.mkdir(exist_ok=True)
for name in MARKERS:
    path=VOLUME/name
    if path.exists():
        require(path.is_file() and path.stat().st_size==0,'Diagnostic control changed; refusing removal')
        (out/name).write_bytes(path.read_bytes())
        require((out/name).read_bytes()==path.read_bytes(),'Backup mismatch')
        path.unlink()
subprocess.run(['sync'],check=True)
require(all(not (VOLUME/name).exists() for name in MARKERS),'Marker removal failed')
(out/'status.json').write_text(json.dumps(dict(markers=list(MARKERS),removed_from_camera=True,backup=str(out),firmware_changed=False),indent=2)+'\n')
print('Three diagnostic markers backed up and removed; photos, dumps and logs retained; camera remains mounted.')
