# Ace Pro 2: initial firmware map and debug investigation

Analysis date: 2026-10-29. All findings below come from the local firmware.
No live camera inspection or external research was performed.

## Main findings

1. The main application uses **ThreadX 64-bit on Ambarella CV5**. The decoded
   image contains `OS: ThreadX 64-bit` and matching OS adaptation/build paths.
   Its entry code disassembles as AArch64.
2. **RT-Thread is inside `aiisp_rtos.bin`**, packaged in the system ROMFS.
   Main-application code refers to loading that file into the AIISP subsystem.
   The AIISP image contains Cortex-M7 sleep/wakeup messages, a plausible ARM
   microcontroller vector table, RT-Thread identification, and Tetras BSP paths.
3. A separate **128 KiB MCU update** is included. Its precise processor and
   responsibilities have not been established.
4. **AmbaShell and USB serial shell code are compiled into the main image.**
   Their availability through the camera's normal USB modes is unconfirmed.
5. A **storage-driven script execution path** exists in the ARM code. It looks
   for `<drive>:\svc_auto_run.ash`, opens an existing file, reads lines, and
   passes them to the shell execution wrapper. Runtime prerequisites remain
   unverified.
6. All identified integrity checks match. **This does not prove that modified
   firmware will be accepted**, or that secure boot is disabled.

## Input and package structure

Input: `Insta360AcePro2FW.bin`, 151,943,857 bytes.

SHA256:

```text
9b5b98818a05b7e9d95dad00990ad0c8e978aa59de80867d6fc59010d5cb7094
```

The tail contains two 84-byte module records followed by a 32-byte footer.
Each module record contains a little-endian size, 32-byte name, 32-byte version,
and 16-byte MD5 digest. The footer contains `WFNITOPS`, module count 2,
four reserved bytes, and an MD5 of every preceding byte in the package.

| Module | Version label | Original file offset | Size | MD5 verified |
|---|---|---:|---:|---|
| CAM | `2.0.51.x` | `0x00000000` | 151,812,585 | Yes |
| MCU | `1.1.30.0` | `0x090c79e9` | 131,072 | Yes |

These are package labels, not versions read from a running camera.

The module table starts at `0x090e79e9`, and the footer at `0x090e7a91`.
The records account for every byte in the package.

## CAM payloads

Each of the four observed payloads has a 256-byte header. Its first words are
CRC32, an apparent version field, an apparent date field, payload length, and
a load-address field. Remaining fields have not all been decoded.

| Content (inferred label) | Header offset | Payload offset | Stored size | Result |
|---|---:|---:|---:|---|
| Main ThreadX application | `0x000005b0` | `0x000006b0` | 20,347,660 | LZ4 decompresses to 65,294,085 bytes |
| DSP/model ROMFS | `0x013681bc` | `0x013682bc` | 90,030,080 | 117 files |
| System/assets ROMFS | `0x069442bc` | `0x069443bc` | 41,390,080 | 367 files |
| Device tree | `0x090bd3bc` | `0x090bd4bc` | 42,285 | FDT parses successfully |

All four payload CRC32 values match their headers. The LZ4 content checksum
also validates. The apparent date word is `0x07ea0710`, consistent with
2026-07-16 if interpreted as year/month/day; that interpretation is tentative.

The ROMFS layout has magic `0x66fc328a`, a file count, and 76-byte directory
records: name[64], size, relative data offset, CRC32. All **484 file CRCs**
match, and all file extents are within their containing ROMFS.

The main header declares slots including BOOTSTRAP, BOOTLOADER, FW_UPDATER,
ARM_TRUST_FW, SYS_SW, SECURE, SYS_DATA, CALIB, USER_SETTING, DRIVE_A/B,
XTB, EXCEPTION_SAVE_LOG, and SYS_SETTING. These are declarations; the update
does not contain independently identified executable payloads for every slot.
In particular, a bootloader implementation has not been extracted here.

Notable files in the system ROMFS:

| File | Original file offset | Size | Interpretation |
|---|---:|---:|---|
| `aiisp_rtos.bin` | `0x08aed3bc` | 1,146,320 | RT-Thread AIISP firmware |
| `aiisp_config.bin` | `0x08c053bc` | 34,592 | AIISP configuration; format not yet decoded |
| `camera_params.json` | See inventory | 699,961 | Camera settings/options data, root key `Iacwa586` |
| `ewres.bin` | See inventory | 12,879,900 | Likely UI resources, based on name and GUI code references |

The full inventory is in `romfs_files.json`; extraction currently selects
the AIISP files and camera parameter JSON rather than copying every asset.

## Debug and startup paths

Offsets in this section refer to the **decompressed main ThreadX image**.
The load address `0x50000` from its header is consistent with ARM64 PC-relative
references. Consequently, an instruction's runtime virtual address is its
decompressed file offset plus `0x50000` for the code examined here.

### Shell

- `0x01b8ea4c`: AmbaShell banner.
- `0x01b8eec8`: `Supported Shell Commands:`.
- `0x01b8f900`: `OS: ThreadX 64-bit`.
- Numerous `Usage: aip ...` strings and unit-test command registration messages
  suggest application-level commands as well as the underlying SDK shell.

### Startup script: strongest current lead

- `0x02477158`: `:\svc_auto_run.ash`.
- Function VA `0x01617000` constructs a drive-qualified filename and checks it.
- At VA `0x016170c4`, it calls the script reader at `0x01617c20`.
- The reader opens the file, reads one byte at a time, handles line endings,
  and passes lines to VA `0x00dcdf40`, which calls the shell processor.
- Storage-monitor code calls the filename/check function at VAs
  `0x0161747c` and `0x0161756c`. The surrounding code includes drive state,
  callback, and once-only state checks; exact enabling conditions remain open.
- A second filename, `:\cvexec.ash` at `0x0243c1a8`, has code references and
  a call to the same script reader in the computer-vision startup path.

This is stronger evidence than a filename string alone. It supports a
candidate path for running existing shell commands without modifying the
firmware package. It does **not** yet prove a file on a user SD card will run,
that the path is enabled on every boot, or that arbitrary native binaries
can be loaded.

See `startup_script_aarch64.txt` for the relevant instruction listings.
No `.ash` file has been created or deployed.

### USB serial and UART

- `0x01c4d068`: `creat cdc_acm_shell_task fail 0x%2x`.
- `0x01c4d0c0`: `AppCdcAcmd_Start(): Broken Shell starts.`.
- `0x01c4d0f0`: `AppCdcAcmd_Stop(): switch back to UART mode.`.
- `0x01c51198`: `AmbaUSBD_RefCdcAcmShell`.
- Descriptors reference CDC-ACM, multiple UART channels, CDC+MSC, and CDC+MTP.
- Application USB-mode strings include SIMPLEUSB, UDISK, WEBCAM, CARDREADER,
  REVERSE_CHARGE, and UACMIC. A serial shell is not an identified normal UI mode.

The device tree enables two UART nodes and marks three additional UART nodes
disabled. This is a hardware-description observation, not evidence of physical
test-pad locations, electrical levels, or an accessible console.

## Update verification and secure boot

Verified offline:

- Package-wide MD5 in the footer.
- CAM module MD5 and MCU module MD5.
- Four payload CRC32 values.
- 484 ROMFS file CRC32 values.
- LZ4 frame checksum during decompression.

The executable contains MD5-related update functions/messages, including
`InsApp_FWPKG_CheckMD5`, `InsApp_FWUpdate_Check_MD5`, and file MD5 pass/fail
messages. CRC32 fields also appear in update diagnostics. These corroborate
the parsed integrity fields but do not fully establish the updater call graph.

Secure-boot provisioning commands and OTP public-key operations also appear
in shell help/code. Their presence shows SDK support for secure boot; it does
not reveal this camera's fuse state. The relevant commands can permanently
change hardware state and are not suitable as exploratory tests.

No firmware-signature verification requirement has been established or ruled
out. TLS RSA/ECDSA strings are not evidence of firmware signing: the same
application includes HTTPS and other TLS users. A complete answer requires
tracing update/boot code and, potentially, observing the device's boot state.

## Linux and Android qualification

The DTB identifies `Ambarella CV5BUB Board` and contains Linux-style bootargs:

```text
ubi.mtd=5 root=ubi0:linux rootfstype=ubifs console=ttyS0 nosmp maxcpus=0
```

Linux/Ambalink and Android compatibility references occur in the application.
However, no Linux kernel, Linux root filesystem, or Android installation has
been positively identified in the mapped update. Shared SDK configuration,
optional components, and software already on the camera are possible
explanations. ThreadX is positively identified; Linux runtime presence is
unresolved.

## Practical next steps

1. Trace script activation conditions and identify a confirmed read-only shell
   command before preparing a minimal SD-card probe.
2. If a camera is connected, inspect its USB descriptors and exposed interfaces
   without sending control or update commands.
3. Trace USB class selection to determine whether CDC shell mode is reachable
   through existing application controls or scripts.
4. Trace updater and boot verification code before considering a firmware patch.

Configuration data, UI resources, and image-processing models are available
for inspection. Their presence makes further research practical, but does not
establish that particular new recording modes or other features are feasible.

## Live camera observation: U-Disk mode

Observed 2026-10-29 with the camera connected to this Mac. This extends the
offline analysis above. Only host registry/disk metadata and directory names
were read; no camera commands, scripts, updates, or file writes were issued.
The operating system has mounted the card read/write, so this is not a claim
that macOS itself cannot write filesystem metadata.

- USB product: `Insta360 Ace Pro 2`; manufacturer: `Arashi Vision`.
- USB vendor/product IDs: `070a:4026`.
- One advertised USB configuration; the active configuration exposes one
  interface: interface 0, alternate setting 0, class `0x08` (mass storage),
  subclass `0x06` (SCSI transparent), protocol `0x50` (bulk-only), two endpoints.
- No CDC serial, ADB, or additional vendor-specific interface is visible in
  this active configuration. No camera serial device appeared under `/dev`.
- The device registry links this exact USB device to `disk7` / `disk7s1` in
  this session; these disk identifiers are temporary and must be rediscovered
  before any future use.
- The card is approximately 63.9 GB, mounted at `/Volumes/Untitled`, filesystem
  exFAT. The partition type is displayed as `Windows_NTFS` by macOS, but the
  detected filesystem is **exFAT**, not NTFS.
- Root directory entries: `DCIM`, `MISC`, `INS_PRINTER`, `.fseventsd`.
  `MISC` contains two recording index files; `INS_PRINTER` is empty. Media file
  contents were not inspected.

Evidence: `usb_udisk_snapshot.json` (compact device/interface tree) and
`usb_udisk_ioreg.plist` (raw camera subtree). This confirms that the normal
U-Disk configuration supplies storage access, without an exposed serial shell.
Other USB modes and the startup-script path remain separate research leads.

## Live startup-script probe: first attempt

On 2026-10-29 the reviewed `svc_auto_run.ash` was installed at the card root
with CRLF endings and this sole command: `mkdir C:\AP2P1029`. The installer
verified the connected camera's identity and disk association, refused
overwrites, read the script back, and established that the marker was absent.
The card was safely ejected, and the user was asked to perform a normal
off/on cycle before reconnecting in U-Disk mode.

After the user reported reconnection, the original 19-byte script remained
unchanged, but **no `AP2P1029` directory appeared**. This attempt did not
confirm script execution. It does not distinguish a skipped script from
an unavailable/failed `mkdir` command, nor establish the installed firmware
version or prove that the script path is disabled.

The verified probe and its AppleDouble metadata sidecar were removed and
their absence checked. No firmware update was performed. Baseline, observed
directory entries, result, and cleanup status are in `script_probe_status.json`.
Local copies of the reviewed probe remain under `probes/` for reference.

Further diagnosis should establish the camera's installed firmware version,
trace storage-monitor startup and command registration order, and compare
that behavior with the bootloader and both supplied application images
before preparing another on-device experiment.
