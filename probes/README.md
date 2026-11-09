# Startup-script execution probe

The reviewed script contains one command:

```text
mkdir C:\AP2P1029
```

The sole intended camera-side effect is creating an empty directory on the
SD card. It does not update firmware or change camera settings. It is a
write-to-card execution probe, not a strictly read-only test.

Evidence in the current decompressed main image:

- Storage table at VA `0x03d1a338`: entries `C,0,0,0`, `D,1,0,0`, `I,2,1,0`.
  The monitor examines SD slot 0, checks insertion/readiness, mounts storage,
  and constructs `C:\svc_auto_run.ash`.
- Storage-monitor function VA `0x01617100`; script-path function
  `0x01617000`; script reader `0x01617c20`.
- The script reader passes lines into the shell execution wrapper at
  `0x00dcdf40`, and then the command processor at `0x00dcce60`.
- The `mkdir` registration at decompressed file offset `0x01e37738`
  points to its name and handler VA `0x00dce860`. The handler accepts a
  drive-qualified path and invokes the filesystem directory-create wrapper.

No additional script-specific password or enable-file check was observed in
the traced path. SD readiness/mount state, task startup, and once-only state
still affect execution. This is static analysis; actual camera execution
is what the probe tests.

The installation helper validates the camera's live USB identity, ties its
disk to the mount point, refuses to replace an existing startup script, and
requires the marker to be absent. It writes the script with CRLF endings,
reads it back, and records the baseline locally. It requires filesystem
permission to write to the mounted camera card.

After installing: eject the card safely from the Mac, disconnect USB, power
the camera off and on normally with the card inserted, wait for startup, then
reconnect in U-Disk mode. An `AP2P1029` directory that was absent beforehand
is positive evidence that the startup script executed. Absence is inconclusive
and needs diagnosis; do not infer that firmware patching is required.

After checking the result, remove only the test's `svc_auto_run.ash` and empty
`AP2P1029` directory from the card. Until removed, the script may attempt the
same directory creation on later boots.
