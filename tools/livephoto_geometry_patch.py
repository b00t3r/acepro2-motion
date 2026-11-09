"""Pinned 2.0.51 edits for Live Photo's still coordinate space and enable path."""
import struct


def instruction(word):
    return struct.pack('<I', word)


def branch(source, target, conditional=False):
    delta = target - source
    bits = 19 if conditional else 26
    if delta % 4 or not -(1 << (bits + 1)) <= delta < (1 << (bits + 1)):
        raise ValueError('Branch target out of range')
    imm = (delta // 4) & ((1 << bits) - 1)
    return instruction(0x54000000 | imm << 5 if conditional else 0x14000000 | imm)


STUB = 0x762bb0
LIVE_FLAG = 0x1262e904  # Same state read by native InsApp_LivePhoto_IsEnable, 0x403820.
page_delta = ((LIVE_FLAG & ~4095) - (STUB & ~4095)) >> 12
if not -(1 << 20) <= page_delta < (1 << 20):
    raise ValueError('ADRP target out of range')
page_imm = page_delta & 0x1fffff
stub = b''.join([
    instruction(0x90000000 | (page_imm & 3) << 29 | (page_imm >> 2) << 5 | 9),
    instruction(0xb9400000 | ((LIVE_FLAG & 4095) // 4) << 10 | (9 << 5) | 9),
    instruction(0x35000000 | (((0x760844 - (STUB + 8)) // 4) & 0x7ffff) << 5 | 9),
    branch(STUB + 12, 0x761154),
])

# The stub occupies one 16-byte alignment gap following RET and preceding the
# next function. Static direct-branch and absolute-pointer audits found no
# references to that gap. x9 is dead at both continuation points: the narrow
# branch redefines it, and the general branch does not read it before calls.
PATCHES = [
    (0x760840, bytes.fromhex('a0480054'), branch(0x760840, STUB, conditional=True)),
    (STUB, bytes(16), stub),
    # Do not reject Live Photo solely because narrow is set; retain factory,
    # origin-mode and photo-resolution capability predicates.
    (0x362780, bytes.fromhex('f9079f1a'), instruction(0x52800039)),
    # Enabling Live Photo must preserve zoom instead of invoking SetNarrow(0).
    (0x37065c, instruction(0x94000000 | (((0x36a340 - 0x37065c) // 4) & 0x3ffffff)),
     bytes.fromhex('1f2003d5')),
]


def apply_to_emulator(harness):
    for address, before, after in PATCHES:
        if bytes(harness.uc.mem_read(address, len(before))) != before:
            raise ValueError(f'Unexpected instruction bytes at {address:x}')
        harness.uc.mem_write(address, after)
