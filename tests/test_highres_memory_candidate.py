"""Native control-flow tests for the scoped memory prerequisite, no hardware."""
import functools
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from unicorn.arm64_const import *
from livephoto_harness import Harness, ROOT, run_livephoto_config
from build_highres_memory_candidate import (patched_image, payload, BASE, HOOK,
    STUB, CTX, RES, LIVE, SOURCE, SOURCE_SHA)
from build_usb_name_candidate import USB_OFFSETS
from build_motion_candidate import sha


@functools.lru_cache(None)
def images():
    old = (ROOT / 'builds/offline-background-save/main_threadx.bin').read_bytes()
    return old, patched_image(old)


def machine(resource=227, live=1):
    h = Harness(images()[1])
    h.uc.mem_map(0x100b5000, 0x1b000)
    h.uc.mem_write(RES, struct.pack('<H', resource))
    h.uc.mem_write(LIVE, bytes([live]))
    return h


def native_allocation(resource=227, live=1, free=0x2d6dac80):
    h = machine(resource, live)
    h.uc.mem_write(CTX + 0x18cee, b'\x01')  # Native dynamic-buffer map enabled.
    calls = {}

    def memory_info(uc):
        for reg, value, fmt in ((UC_ARM64_REG_X0, 0xd0525300, '<Q'),
                                (UC_ARM64_REG_X1, 0x2d6dad00, '<I'),
                                (UC_ARM64_REG_X2, free, '<I')):
            uc.mem_write(uc.reg_read(reg), struct.pack(fmt, value))
        return 0

    def allocate(uc):
        calls['requested'] = uc.reg_read(UC_ARM64_REG_X0)
        return 0xd0525380

    def copy_pointer(uc):
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X0),
                     bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X1), 8)))
        return 0

    def register(uc):
        calls['registered'] = [uc.reg_read(r) for r in (UC_ARM64_REG_X0,
            UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4)]
        return 0

    h.mocks = {0x1615520: lambda uc: 0, 0xdca900: memory_info,
                0xdcc460: lambda uc: 0, 0xdca4c0: allocate,
                0x1222b20: copy_pointer, 0x1615760: register}
    h.uc.reg_write(UC_ARM64_REG_X0, 0)
    h.run(0x1524ea0)
    return calls


class HighResMemoryCandidateTests(unittest.TestCase):
    def test_exact_source_and_change_scope(self):
        self.assertEqual(sha(SOURCE.read_bytes()), SOURCE_SHA)
        before, after = images()
        expected = bytearray(before)
        from livephoto_geometry_patch import branch
        expected[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, STUB)
        expected[STUB-BASE:STUB-BASE+len(payload())] = payload()
        for at in USB_OFFSETS:
            expected[at:at+18] = b'Insta360 Ace Pro X'
        self.assertEqual(after, expected)

    def test_real_native_live_config_reaches_only_intended_gate(self):
        for resource in (226, 227, 228):
            cfg = run_livephoto_config(resource, image_data=images()[1], include_encoding=True)
            packed = bytes.fromhex(cfg['packed_config_hex'])
            h = machine()
            h.uc.mem_write(CTX + 0x18cfc, packed)
            h.stops[HOOK+4] = 'returned_to_allocator'
            h.run(HOOK)
            expected = 0x0fff8000 if resource == 227 else 0x1fff8000
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_X2), expected)

    def test_allocator_registers_smaller_buffer_for_4x3_live_only(self):
        result = native_allocation()
        self.assertEqual(result['requested'], 0x0fff8000)
        self.assertEqual(result['registered'], [1, 0xd0525380, 0x0fff8000, 0xd0525380, 0x0fff0000])

    def test_ordinary_video_other_ratios_and_live_off_remain_native(self):
        for resource, live in ((21, 1), (183, 0), (227, 0), (226, 1), (228, 1)):
            with self.subTest(resource=resource, live=live):
                result = native_allocation(resource, live)
                self.assertEqual(result['requested'], 0x1fff8000)
                self.assertEqual(result['registered'][-1], 0x1fff0000)

    def test_native_free_memory_bound_is_retained(self):
        result = native_allocation(free=64*1024**2)
        self.assertEqual(result['requested'], 64*1024**2)
        self.assertEqual(result['registered'][-1], 64*1024**2)

    def test_hook_preserves_stack_flags_and_all_other_registers(self):
        for resource, live in ((227, 1), (227, 0), (21, 1)):
            h = machine(resource, live)
            regs = [getattr(sys.modules[__name__], 'UC_ARM64_REG_X%d' % i) for i in range(31)]
            for i, reg in enumerate(regs):
                h.uc.reg_write(reg, 0x1234000000000000 + i)
            h.uc.reg_write(UC_ARM64_REG_NZCV, 0xa0000000)
            before = [h.uc.reg_read(r) for r in regs]
            sp = h.uc.reg_read(UC_ARM64_REG_SP)
            h.stops[HOOK+4] = 'returned_to_allocator'
            h.run(HOOK)
            expected = before[:]
            expected[2] = 0x0fff8000 if resource == 227 and live else 0x1fff8000
            self.assertEqual([h.uc.reg_read(r) for r in regs], expected)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_SP), sp)
            self.assertEqual(h.uc.reg_read(UC_ARM64_REG_NZCV), 0xa0000000)

    def test_capture_colour_and_encoder_settings_are_unchanged(self):
        before, after = images()
        for start, end in ((0x287a80, 0x287e5c), (0x755cb4, 0x755d24),
                            (0x11c1e40, 0x11c2240), (0x50240, 0x50f80),
                            (0x2552020, 0x2552bb0)):
            self.assertEqual(before[start-BASE:end-BASE], after[start-BASE:end-BASE])
        for resource in (226, 227, 228):
            for narrow in (0, 1):
                old = run_livephoto_config(resource, narrow, image_data=before, include_encoding=True)
                new = run_livephoto_config(resource, narrow, image_data=after, include_encoding=True)
                self.assertEqual(old, new)


if __name__ == '__main__':
    unittest.main()
