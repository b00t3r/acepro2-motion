# Bootloader, recovery, and validation investigation

2026-10-29. Static analysis only; nothing was sent to the camera.
The user reports installed application firmware **2.0.51**.

## Conclusions

The supplied **2.0.50 CAMBLD package** contains a bootstrap and an AArch64
bootloader. The bootloader has a path that loads a separate firmware updater
from **internal NAND**, selected by a boot flag. It also has a flag-gated
watchdog path that changes which user partition table is active.

This is evidence of recovery/update machinery, but **does not establish an
automatic, SD-only recovery mode for every operating-system crash**. No SD
installation-file search was identified in the paths examined. Such a search
could occur in the separately installed updater, whose image has not been
identified in the supplied packages.

The traced bootloader image-load paths use CRC32 and decompression. No
cryptographic image-signature check was identified in those paths. That
does not establish that unsigned firmware can boot: ROM, bootstrap, secure
firmware, or updater checks remain possible and are not fully characterized.

The bootloader extracted here is from the **older update**. The actual
bootloader version installed on the camera has not been read. Application
version 2.0.51 does not establish the installed bootloader version.

## Extracted stages and verification

| Stage | CAMBLD payload offset | Length | Header load address | CRC32 |
|---|---:|---:|---:|---|
| Bootstrap | `0x000006b0` | 16,384 | `0x00000000` | `12cc7eaf`, verified |
| Bootloader | `0x000047b0` | 83,456 | `0x10000000` | `8738156c`, verified |

Their headers and payloads account for the entire CAMBLD package after its
outer header. Extracted images are under `previous/extracted/`. The source
file hash is checked before and after analysis.

## What chooses the updater?

At bootloader VA `0x100019e0`, a call to `0x1000c440` tests whether the 32-bit
word at address `0x110` equals the word at offset `+4` in the active user
partition table.

- **Unequal:** follow the normal main-image loading path.
- **Equal:** branch to XTB handling, then the separate updater-loading path.

The equal branch includes XTB and backup-XTB checks. Both subsequently lead
to updater loading; XTB is not an SD installation filename in this path.

In the current application's `InsMw_FwUpdate_SetBldMagicCode` implementation
(function VA `0x002fcda0`), the code reads the same `0x110` word and writes it
into the partition-table word at `+4`, then calls a table-write wrapper.
This is direct evidence connecting the application's update-selection code
with the bootloader comparison. The memory word's earlier initialization
and every caller of the application function have not yet been traced.

No physical button combination for entering this path has been established.
No boot flags or partition tables were changed during this investigation.

## Where are the images loaded from?

At `0x10001b30`, the bootloader obtains **system partition 2**, whose declared
name is `FW_UPDATER`, through partition-entry helper `0x1000bd40`. The
following code reads it through the NAND partition-read path, checks the
stored payload CRC, and decompresses it into its load destination.

The main application is obtained through **user partition 1**, declared
`SYS_SW`, and follows a similar read/CRC/decompression path. The word
"Kernel" in bootloader messages refers to this boot target; it is not
evidence that the main application runs Linux.

The supplied CAM application updates do not include a separately identified
system-partition-2 `FW_UPDATER` executable. A slot declared in the update
header is not proof that its payload is included. Consequently, we cannot
yet establish whether the installed updater scans SD, supports USB input,
or performs additional validation.

The bootloader includes the diagnostic recommending reburning firmware by
USB mode, but that string is not enough to identify the transport's entry
sequence or prove a host-accessible USB recovery protocol.

## Boot failures and watchdog behavior

The `Boot failed!` strings at bootloader VAs `0x10002180` and `0x100021f0`
are reached when a branch into a boot target **returns**. The code prints
the error and returns; no direct SD-card scan is visible there.
This does not establish what happens after an application hangs or crashes
without returning to the bootloader.

There is a watchdog-related callback at `0x100044e0`, referenced through the
boot callback table. It is gated by a reserved configuration flag and emits
`Watchdog test flag is enabled`. When its reset-status condition is met,
it changes active user partition table 0/1, with messages such as:

```text
# WDT reset flag detected, set PTB to 1
# WDT reset flag detected, set PTB to 0
```

This establishes an alternate-partition-table mechanism in the code. It
does not prove full duplicate application images, a guaranteed rollback
policy, or automatic recovery from every crash. Whether the flag is enabled
on this camera is unknown.

The CRC mismatch helper at `0x10001100` is also conditional on runtime state.
It updates a persistent hardware value and calls a restart-related helper.
Its name/role is inferred from callers and instructions. Do not model every
CRC mismatch as an unconditional switch into an SD installer.

A UART console path is present (`amboot>`). Its input loop supports early
serial interruption and commands such as partition-table display and boot.
This is not a confirmed physical-button recovery sequence. UART test-pad
locations, electrical details, and live accessibility are still unknown.

## Which validation checks are established?

| Layer | Established locally | Still unknown |
|---|---|---|
| Update package | Whole-package and per-module MD5 match | Complete installer acceptance policy |
| Stored boot targets | NAND reads, stored CRC32 comparison, LZ4-style decompression | Checks elsewhere in the boot chain |
| Boot selection | Boot flag and active partition-table logic | Actual flags and partition contents on the camera |
| Signature enforcement | No signature verification identified in traced loader paths | ROM/bootstrap/secure-firmware/updater policy |

The CRC wrapper at `0x10004ee0` initializes the accumulator to all ones,
processes the data, and complements the result. Its helpers at `0x10005da0`
use ARM `crc32x`, `crc32w`, `crc32h`, and `crc32b` instructions. These are
integrity checks, not public-key signature verification.

In the current **2.0.51 application's package digest checker** at
`0x00359900`, the code hashes `package_length - 16` bytes and compares a
16-byte result against the final 16 bytes. This agrees with the package-wide
MD5 field already verified offline. The package-preparation path calls it
at `0x0035a758` and handles failure. This function alone does not establish
that no additional checks are performed later.

Two generic `smc #0` stubs exist in the bootloader, but no direct callers were
identified for them in the scanned image. Their mere presence is not
evidence of signature verification, and absence of direct callers does not
exclude indirect calls or checks in earlier stages.

## What this means for modifying the camera

We have a concrete boot/update architecture to investigate. We do **not**
yet have a verified method to recover a failed modification, or proof that
a rebuilt image would be accepted. Nothing in this analysis calls for
deliberately damaging the installed firmware to trigger recovery.

The next useful offline target is the **2.0.51 application's complete update
acceptance and write path**, followed by identifying a legitimate source for
the separately installed updater image. A read-only boot log would also help
establish the actual bootloader version, selected path, and current flags,
if an accessible console is found.

## Reproduce and inspect evidence

From the project root:

```sh
.venv/bin/python tools/inspect_bootloader.py
```

- `bootloader_manifest.json`: extraction offsets, hashes, and known functions.
- `bootloader_recovery_aarch64.txt`: selected loader, flag, CRC, watchdog,
  and UART-console instruction ranges.
- `update_flag_and_digest_aarch64.txt`: current application's boot-flag setter
  and package digest checker.
- `bootloader_string_refs.json`: candidate references to relevant messages.
- `bootloader_strings.tsv`: readable strings and virtual addresses.
- `bootloader_linear_aarch64.txt`: linear decoding, **including data regions
  that may look like instructions**; use the targeted listings for findings.

Function names and role descriptions are analyst labels unless explicitly
identified by strings. Static paths have not been exercised on the camera.
