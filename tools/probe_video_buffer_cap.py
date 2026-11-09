"""Offline feasibility probe of the native encoder-buffer allocation cap.

Only an emulator copy of one instruction changes. No update is produced.
This is NOT a complete patch: Live Photo-only gating, all buffer consumers,
larger streaming allocations and hardware recording remain unverified.
"""
import json
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X21
from livephoto_harness import Harness, BASE, image, ROOT

CAP_INSTRUCTION = 0x1524f1c
OLD_WORD = 0x321137e2  # mov w2, #0x1fff8000
PROPOSED_WORD = 0x321133e2  # mov w2, #0x0fff8000


def allocation_cap(free_bytes, proposed=False):
    if not 0 <= free_bytes < 2**32:
        raise ValueError('Native free-size input must fit uint32')
    h = Harness()
    if struct.unpack_from('<I', image(), CAP_INSTRUCTION - BASE)[0] != OLD_WORD:
        raise ValueError('Unexpected native allocator instruction')
    if proposed:
        h.uc.mem_write(CAP_INSTRUCTION, struct.pack('<I', PROPOSED_WORD))
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0x54, struct.pack('<I', free_bytes))
    h.mocks[0xdcc460] = lambda uc: 0  # Log only; allocation not reached.
    h.stops[0x1524f3c] = 'selected_size_before_malloc'
    h.run(0x1524f18)
    return h.uc.reg_read(UC_ARM64_REG_X21)


def audit():
    data = json.loads((ROOT / 'analysis/motion-resolution-audit/fullheight-path.json').read_text())
    memory = data['recorded_memory_layouts']
    free = 0x2d6dac80  # Logged free bytes immediately before the original allocation.
    old, proposed = allocation_cap(free), allocation_cap(free, proposed=True)
    saved = old - proposed
    live_pool = memory['layouts'][0]['still_pool_bytes']
    full_pool = memory['layouts'][1]['still_pool_bytes']
    dis = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    return dict(
        native_instruction=str(next(dis.disasm(struct.pack('<I', OLD_WORD), CAP_INSTRUCTION)).op_str),
        emulator_only_instruction=str(next(dis.disasm(struct.pack('<I', PROPOSED_WORD), CAP_INSTRUCTION)).op_str),
        original_reservation_bytes=old, proposed_reservation_bytes=proposed,
        theoretical_bytes_released=saved,
        recorded_live_still_pool_bytes=live_pool,
        recorded_ordinary_full_still_pool_bytes=full_pool,
        theoretical_live_pool_if_only_this_reservation_changed=live_pool + saved,
        margin_over_recorded_full_photo_pool_before_streaming_changes=live_pool + saved - full_pool,
        firmware_created=False, camera_changed=False,
        limits=['A standalone arithmetic probe, not a validated memory layout.',
                'Does not include the larger continuous sensor/video buffers required by a full-resolution stream.',
                'Does not validate minimum bitstream capacity, pre-recording, wrapping, JPEG sharing or other consumers.',
                'No Live Photo-only gating has been designed or tested; never apply this instruction globally.'])


if __name__ == '__main__':
    report = audit()
    (ROOT / 'analysis/motion-resolution-audit/video-buffer-feasibility.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
