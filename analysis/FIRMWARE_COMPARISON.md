# Firmware comparison

Files analyzed without modification:

| | Current supplied package | Previous supplied package |
|---|---|---|
| File | `Insta360AcePro2FW.bin` | `Insta360AcePro2FW.bin.old.bin` |
| CAM version label | `2.0.51.x` | `2.0.50.x` |
| MCU version label | `1.1.30.0` | `1.1.29.0` |
| CAMBLD module | Not included | `2.0.50.x`, 101,808 bytes |
| ROMFS entries | 484 | 484 |
| Integrity checks | All identified checks match | All identified checks match |

Previous input SHA256:
`6ad878a7e756ea0e68627ecd2bb016dd4f5405b625e795dc6b7ab9355327a9aa`

Both main images contain ThreadX identification, USB CDC shell code references,
and `svc_auto_run.ash` / `cvexec.ash` references. The script-path function in
the previous main image is at VA `0x01614d00`; the corresponding current
function is at VA `0x01617000`. This is static evidence in both packages,
not confirmation of the version currently running on the camera.

By filename, size, and CRC32, all ROMFS entries are unchanged except
`ewres.bin`, likely the UI resource bundle. No filenames were added or removed.
CRC equality is a useful first-pass comparison; a byte-for-byte comparison
of every embedded file has not been performed.

The older update also includes a CAMBLD package. It has been extracted to
`previous/extracted/cam_bootloader_package.bin`. It contains bootloader prompt
`amboot>`, CRC diagnostics, partition definitions, and boot-up messages.
Its internal payloads and verification flow remain to be analyzed. It has
not been installed on the camera.

Reproduce the older firmware analysis:

```sh
.venv/bin/python tools/inspect_firmware.py Insta360AcePro2FW.bin.old.bin --out analysis/previous
```
