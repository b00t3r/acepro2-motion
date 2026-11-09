"""Stage only the fixed disposable rename-diagnostic files; never overwrite."""
from pathlib import Path
import os

root=Path('/Volumes/Untitled')
probe=root/'CXR7139'
if not root.is_mount(): raise SystemExit('Camera volume is not mounted')
probe.mkdir()  # Refuse an existing directory, including a symlink.
for name, data in [('S.TST',b'CODEX7139-S'),('D.TST',b'CODEX7139-D'),('A.TST',b'CODEX7139-A')]:
    path=probe/name
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if path.read_bytes()!=data: raise SystemExit('Fixture verification failed: '+name)
print('Disposable fixtures verified; activation marker written last.')
