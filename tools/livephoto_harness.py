#!/usr/bin/env python3
"""Execute selected stock ARM64 routines with explicit software-only mocks.

This is not a camera/ISP emulator. Gate tests stop before capture changes.
The optional gate edit exists only in emulator memory, never in an update.
"""
import functools
import hashlib
import json
import struct
from dataclasses import dataclass, asdict
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_PC,
    UC_ARM64_REG_S0, UC_ARM64_REG_CPACR_EL1,
    UC_ARM64_REG_X23, UC_ARM64_REG_X25, UC_ARM64_REG_X26, UC_ARM64_REG_X27,
    UC_ARM64_REG_X6, UC_ARM64_REG_X8, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21,
)

ROOT = Path(__file__).resolve().parent.parent
BASE = 0x50000
EXPECTED_IMAGE_SHA = 'da22a8a0bf105a26192281dc563c7c38a169fcbc1778ee565007143bdc39a02e'
CONTEXT = 0x50000000
STACK = 0x70000000
RETURN = 0x71000000
GATE_ENTRY = 0x369d40
ALLOW = 0x36a030
DENY = 0x369eac
LIVEPHOTO_COMPARE = 0x369ea0
ZOOM_FORWARD = 0x363d80


@functools.lru_cache(maxsize=1)
def image():
    data = (ROOT / 'analysis/extracted/main_threadx.bin').read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_IMAGE_SHA:
        raise ValueError('Harness addresses require the original supplied 2.0.51 image')
    return data


def float_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def reg_float(uc):
    return struct.unpack('<f', struct.pack('<I', uc.reg_read(UC_ARM64_REG_S0)))[0]


@dataclass
class GateInputs:
    livephoto: bool = False
    record_state: int = 0
    switch_busy: int = 0
    factory_mode_value: int = 2
    capture_mode_value: int = 0
    capture_type_value: int = 0
    capture_submode_value: int = 0
    actual_capture_mode_value: int = 0
    requested_narrow: int = 1
    current_narrow: int = 0
    # The actual UI narrow/2x caller passes (1, -1.0); scalar zoom is separate.
    requested_ratio: float = -1.0
    configured_ratio_percent: int = 100
    narrow_supported: bool = True


class Harness:
    def __init__(self, image_data=None):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        data = image() if image_data is None else image_data
        if len(data) != len(image()):
            raise ValueError('Candidate image must retain the pinned original image size')
        self.uc.mem_map(BASE, (len(data) + 4095) & ~4095)
        self.uc.mem_write(BASE, data)
        self.uc.mem_map(CONTEXT, 0x20000)
        self.uc.mem_map(STACK, 0x20000)
        self.uc.mem_map(RETURN, 0x1000)
        self.uc.mem_map(0x1262e000, 0x1000)
        self.uc.mem_map(0x1264f000, 0x1000)
        self.uc.reg_write(UC_ARM64_REG_SP, STACK + 0x10000)
        self.uc.reg_write(UC_ARM64_REG_X30, RETURN)
        self.uc.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)
        self.calls = []
        self.steps = 0
        self.outcome = None
        self.fault = None
        self.mocks = {}
        self.stops = {RETURN: 'returned'}
        self.uc.hook_add(UC_HOOK_CODE, self.hook)

    def hook(self, uc, address, size, _):
        self.steps += 1
        if address in self.stops:
            self.outcome = self.stops[address]
            uc.emu_stop()
        elif address in self.mocks:
            self.calls.append(address)
            try:
                result = self.mocks[address](uc)
                uc.reg_write(UC_ARM64_REG_X0, 0 if result is None else result)
                uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))
            except Exception as exc:
                self.fault = exc
                uc.emu_stop()

    def run(self, entry, max_instructions=20000):
        self.uc.emu_start(entry, RETURN + 4, timeout=2_000_000, count=max_instructions)
        if self.fault:
            raise self.fault
        if self.outcome is None:
            raise RuntimeError('Routine did not reach an expected boundary within limits')

    def config_mock(self, narrow, ratio_percent):
        def get(uc):
            if uc.reg_read(UC_ARM64_REG_X0) != 0x1c:
                raise ValueError('Unexpected configuration ID')
            if uc.reg_read(UC_ARM64_REG_X2) != 8:
                raise ValueError('Unexpected zoom configuration size')
            data = bytearray(8)
            data[4] = narrow
            struct.pack_into('<H', data, 5, ratio_percent)
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), bytes(data))
            return 0
        return get


def run_gate(inputs=GateInputs(), in_memory_livephoto_edit=False, image_data=None,
             execute_support_check=False, through_config_write=False, via_gui_bridge=False):
    h = Harness(image_data)
    uc = h.uc
    h.stops.update({ALLOW: 'accepted_by_gate', DENY: 'rejected_by_gate'})
    if through_config_write:
        del h.stops[ALLOW]
        h.stops.update({0x36a248: 'rejected_by_support_check',
                        0x2e4ae0: 'zoom_config_write_requested'})
    if in_memory_livephoto_edit == 'always_factory_compare':
        if bytes(uc.mem_read(0x369ea4, 4)) != bytes.fromhex('0008427a'):
            raise ValueError('Expected conditional factory-mode comparison')
        uc.mem_write(0x369ea4, bytes.fromhex('00e8427a'))
    elif in_memory_livephoto_edit:
        before = bytes(uc.mem_read(LIVEPHOTO_COMPARE, 4))
        if before != bytes.fromhex('df020071'):
            raise ValueError('Expected cmp w22, #0')
        # cmp w22, w22 always sets equality. Register 31 in the immediate
        # encoding would mean WSP, not WZR. Other checks remain intact.
        uc.mem_write(LIVEPHOTO_COMPARE, bytes.fromhex('df02166b'))
    uc.reg_write(UC_ARM64_REG_X0, inputs.requested_narrow & 0xffffffff)
    uc.reg_write(UC_ARM64_REG_S0, float_bits(inputs.requested_ratio))
    uc.mem_write(0x1262e904, struct.pack('<I', int(inputs.livephoto)))
    uc.mem_write(0x25e78d0, struct.pack('<I', inputs.switch_busy))

    def capture_config(uc):
        if uc.reg_read(UC_ARM64_REG_X0) != 0x12:
            raise ValueError('Unexpected capture configuration ID')
        data = bytearray(20)
        # INS_CFG_COMMON_ID_CAMMODE: Mode, SubMode, OriginMode, ActualMode,
        # followed by two preset halfwords. The handler reads OriginMode.
        struct.pack_into('<4I', data, 0, inputs.capture_type_value,
                         inputs.capture_submode_value, inputs.capture_mode_value,
                         inputs.actual_capture_mode_value)
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), bytes(data))
        return 0

    def factory(uc):
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X0), struct.pack('<I', inputs.factory_mode_value))
        return 0

    h.mocks = {
        0x28e120: lambda uc: CONTEXT,
        0x2e41a0: capture_config,
        0x300580: lambda uc: inputs.record_state,
        0x361900: lambda uc: int(inputs.narrow_supported),
        0x3501c0: factory,
        0x2e4380: h.config_mock(inputs.current_narrow, inputs.configured_ratio_percent),
        0x2639a0: lambda uc: 0,
        0x71b880: lambda uc: 0,
    }
    if execute_support_check:
        del h.mocks[0x361900]
        # Explicit controlled feature result; no support decision is mocked.
        h.mocks[0x373a60] = lambda uc: 0
    if through_config_write:
        h.mocks.update({0x26fe00: lambda uc: 0, 0x341fc0: lambda uc: 0,
                         0x35ffa0: lambda uc: 0})
    # 0x403820, the live-photo-state getter, runs as real firmware code.
    if via_gui_bridge:
        # Real GuiMwCB_SetNarrowZoom input record: integer value at +0xc.
        uc.mem_write(CONTEXT + 0xc, struct.pack('<I', inputs.requested_narrow))
        uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
        uc.reg_write(UC_ARM64_REG_X1, CONTEXT + 0x400)
    h.run(0x4b4140 if via_gui_bridge else GATE_ENTRY)
    result = {'inputs': asdict(inputs), 'in_memory_livephoto_edit': in_memory_livephoto_edit,
            'outcome': h.outcome, 'instruction_count': h.steps,
            'mocked_calls': [hex(x) for x in h.calls],
            'stopped_before_capture_changes': not through_config_write,
            'support_check_executed': execute_support_check,
            'gui_bridge_executed': via_gui_bridge,
            'hardware_not_executed': True}
    if h.outcome == 'zoom_config_write_requested':
        if uc.reg_read(UC_ARM64_REG_X0) != 0x1c or uc.reg_read(UC_ARM64_REG_X2) != 8:
            raise ValueError('Unexpected config write boundary')
        data = bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X1), 8))
        result['requested_config'] = {'narrow': data[4],
                                      'ratio_percent': struct.unpack_from('<H', data, 5)[0]}
    return result


def run_zoom_forward(configured_percent=200, requested_ratio=-1.0, notify=True, setter_error=0):
    """Run the real app zoom-forwarding helper; replace its service boundary."""
    h = Harness()
    calls = []
    notifications = []
    h.uc.reg_write(UC_ARM64_REG_S0, float_bits(requested_ratio))
    h.uc.reg_write(UC_ARM64_REG_X0, 0 if notify else 1)

    def service(uc):
        calls.append(reg_float(uc))
        return setter_error

    def notification(uc):
        notifications.append({'event': uc.reg_read(UC_ARM64_REG_X0), 'ratio': reg_float(uc)})
        return 0

    h.mocks = {
        0x2e4380: h.config_mock(0, configured_percent),
        0x2639a0: lambda uc: 0,
        0x71b880: lambda uc: 0,
        0x29fb60: service,
        0x4c2740: notification,
    }
    h.run(ZOOM_FORWARD)
    return {'service_ratios': calls, 'notifications': notifications,
            'return_value': h.uc.reg_read(UC_ARM64_REG_X0), 'instruction_count': h.steps,
            'hardware_service_mocked': True}


def run_livephoto_config(resolution_id=226, narrow=1, preserve_narrow=False, image_data=None,
                         config_overrides=None, include_encoding=False, extra_mocks=None):
    """Run the real Live Photo config rewrite and real resolution lookup.

    Resolution 226 is the dedicated 3840x2160/30 Live Photo entry.
    Resolution 21 is ordinary 4K; 178 is a 4:3 starlapse entry.
    These are controlled software profiles, not a captured live camera state.
    """
    h = Harness(image_data)
    if preserve_narrow:
        if bytes(h.uc.mem_read(0x401540, 4)) != bytes.fromhex('7f3600b9'):
            raise ValueError('Expected str wzr, [x19, #0x34]')
        # Preserve the narrow halfword, still clear its adjacent crop field.
        h.uc.mem_write(0x401540, struct.pack('<I', 0x79006e7f))
    cfg = CONTEXT + 0x1000
    data = bytearray(0x70)
    struct.pack_into('<H', data, 6, resolution_id)
    struct.pack_into('<H', data, 8, 192)
    struct.pack_into('<H', data, 10, 18)
    struct.pack_into('<H', data, 0x34, narrow)
    struct.pack_into('<H', data, 0x36, 7)
    h.uc.mem_write(cfg, bytes(data))
    h.uc.reg_write(UC_ARM64_REG_X0, cfg)

    def config(uc):
        key = uc.reg_read(UC_ARM64_REG_X0)
        size = uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) not in [(0x3d, 4), (0x24, 1), (0x1b, 8)]:
            raise ValueError(f'Unexpected Live Photo config read: {key:x}/{size}')
        value = (config_overrides or {}).get(key, bytes(size))
        if len(value) != size:
            raise ValueError('Config override has incorrect size')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), value)
        return 0

    h.mocks = {0x2e4380: config, 0x28d840: lambda uc: 0,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.mocks.update(extra_mocks or {})
    # 0x361100, the compiled resource lookup, executes without a mock.
    h.run(0x401480)
    after = bytes(h.uc.mem_read(cfg, len(data)))
    half = lambda offset: struct.unpack_from('<H', after, offset)[0]
    result = {'input_resolution_id': resolution_id, 'input_narrow': narrow,
            'livephoto_flag': after[0xe], 'narrow_flag': half(0x34),
            'adjacent_crop_field': half(0x36),
            'resource_ids': [half(8), half(10)],
            'dimensions': [half(0x1a), half(0x1c)], 'instruction_count': h.steps,
            'mocked_calls': [hex(x) for x in h.calls],
            'resolution_lookup_mocked': False, 'hardware_not_executed': True}
    if include_encoding:
        result.update(target_bitrate=struct.unpack_from('<I', after, 0x20)[0],
                      bitrate_control=struct.unpack_from('<I', after, 0x24)[0],
                      fps_numerator=struct.unpack_from('<I', after, 0x2c)[0],
                      fps_denominator=half(0x30), packed_config_hex=after.hex())
    return result


def run_video_zoom_gate(narrow=0, feature_8=True, stream=0, resolution_id=226,
                        capture_mode=2, capture_submode=0):
    """Execute the native video permission check, with an explicit feature mock.

    The meaning of feature query 8 is not yet established; exercise both states.
    A successful result is software permission, not evidence of ISP cropping.
    """
    h = Harness()
    h.uc.reg_write(UC_ARM64_REG_X0, stream)
    cfg = CONTEXT + 0x18cfc
    h.uc.mem_write(cfg, struct.pack('<HH', capture_mode, capture_submode))
    h.uc.mem_write(cfg + 6, struct.pack('<H', resolution_id))
    h.uc.mem_write(cfg + 0x34, struct.pack('<H', narrow))

    def feature(uc):
        if uc.reg_read(UC_ARM64_REG_X0) != 8:
            raise ValueError('Unexpected feature query')
        return int(feature_8)

    h.mocks = {0x28e120: lambda uc: CONTEXT, 0x28ff60: feature,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.run(0x778240)
    return {'allowed': bool(h.uc.reg_read(UC_ARM64_REG_X0)),
            'feature_8_mocked': feature_8, 'instruction_count': h.steps}


def run_still_request_fragment(narrow=0):
    """Execute only the native request-building fragment, with seeded stack.

    This demonstrates field forwarding; it does not execute sensor selection,
    the complete still builder, or image capture.
    """
    h = Harness()
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0xaf, bytes([narrow]))
    h.uc.reg_write(UC_ARM64_REG_X23, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X25, 1)
    h.uc.reg_write(UC_ARM64_REG_X26, 1)
    h.uc.reg_write(UC_ARM64_REG_X27, 0)
    h.stops[0x28254c] = 'request_fields_written'
    h.run(0x2824e0)
    return {'request_narrow': h.uc.mem_read(sp + 0x187, 1)[0],
            'instruction_count': h.steps, 'fragment_only': True}


def run_profile_selection_fragment(capture_id=31):
    """Run the native descriptor-ID search, stopping before profile copying.

    Capture IDs are metadata, not array indices. Later callbacks may further
    modify the descriptor; this only establishes the initial template choice.
    """
    h = Harness()
    table = 0x1e94cd0
    h.uc.mem_write(CONTEXT + 0x48, struct.pack('<I', 60))
    h.uc.mem_write(CONTEXT + 0x68, struct.pack('<Q', table))
    h.uc.reg_write(UC_ARM64_REG_X19, CONTEXT)
    h.uc.reg_write(UC_ARM64_REG_X0, capture_id)
    h.uc.reg_write(UC_ARM64_REG_X6, 60)
    h.stops[0x2933d0] = 'template_search_complete'
    h.run(0x293390)
    index = h.uc.reg_read(UC_ARM64_REG_X8)
    address = table + index * 0x18e38
    if struct.unpack('<H', h.uc.mem_read(address + 0x18cfa, 2))[0] != capture_id:
        raise ValueError('No matching capture template')
    read_string = lambda offset: bytes(h.uc.mem_read(address + offset, 128)).split(b'\0')[0].decode()
    return {'capture_id': capture_id, 'template_index': index,
            'template_name': read_string(0x20), 'topology': read_string(0xa0),
            'instruction_count': h.steps, 'fragment_only': True}


def run_still_fov_selection(narrow=0, configured_fov=2):
    """Run the real still FOV selection through its call boundary.

    Includes the configuration read and narrow override, but stops before
    calculating warp parameters or touching the image processor.
    """
    h = Harness()
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0xe0, struct.pack('<Q', CONTEXT))
    h.uc.mem_write(CONTEXT + 0x18d12, struct.pack('<H', 1))

    def config(uc):
        data = bytearray(8)
        struct.pack_into('<I', data, 0, configured_fov)
        data[4] = narrow
        if uc.reg_read(UC_ARM64_REG_X0) != 0x1c or uc.reg_read(UC_ARM64_REG_X2) != 8:
            raise ValueError('Unexpected still FOV configuration read')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), bytes(data))
        return 0

    h.mocks = {0x2e4380: config}
    h.stops[0x760328] = 'before_fov_calculation'
    h.run(0x7602bc)
    return {'selected_fov': h.uc.reg_read(UC_ARM64_REG_X1),
            'instruction_count': h.steps, 'hardware_not_executed': True}


def run_still_sensor_selection(narrow=0, sensor_mode=9, photo_mode=0,
                               image_data=None, livephoto=False):
    """Run native still sensor-mode selection with controlled camera state."""
    h = Harness(image_data)
    h.uc.mem_write(0x1262e904, struct.pack('<I', int(livephoto)))
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0xaf, bytes([narrow]))
    h.uc.mem_write(sp + 0xb3, struct.pack('<I', photo_mode))
    h.uc.mem_write(CONTEXT + 0x18800, struct.pack('<I', sensor_mode))
    # The fragment begins after the context getter has returned in x28.
    from unicorn.arm64_const import UC_ARM64_REG_X28
    h.uc.reg_write(UC_ARM64_REG_X28, CONTEXT)
    h.stops[0x28245c] = 'sensor_mode_selected'
    h.run(0x282410)
    return {'sensor_mode': struct.unpack('<I', h.uc.mem_read(CONTEXT + 0x18800, 4))[0],
            'instruction_count': h.steps, 'fragment_only': True}


def run_livephoto_support_check(narrow=0, factory_mode=2, origin_mode=12,
                                photo_resolution_id=2, allow_zoom=False, image_data=None):
    """Execute the backend Live Photo support decision with controlled config.

    This does not emulate GUI notifications or asynchronous mode transitions.
    """
    h = Harness(image_data)
    h.uc.reg_write(UC_ARM64_REG_X0, origin_mode)
    h.uc.reg_write(UC_ARM64_REG_X1, photo_resolution_id)
    if allow_zoom:
        # Replace only the boolean derived from narrow != 1. Other capability
        # predicates are still executed by the original firmware instructions.
        if bytes(h.uc.mem_read(0x362780, 4)) != bytes.fromhex('f9079f1a'):
            raise ValueError('Unexpected Live Photo support predicate')
        h.uc.mem_write(0x362780, struct.pack('<I', 0x52800039))
    def config(uc):
        key = uc.reg_read(UC_ARM64_REG_X0)
        size = uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) == (1, 12):
            data = struct.pack('<III', factory_mode, 0, 0)
        elif (key, size) == (0x1c, 8):
            data = bytearray(8)
            data[4] = narrow
            struct.pack_into('<H', data, 5, 100)
            data = bytes(data)
        else:
            raise ValueError(f'Unexpected support-check config {key:x}/{size}')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), data)
        return 0
    h.mocks = {0x2e41a0: config, 0x2e4380: config,
               0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.run(0x362700)
    return {'supported': bool(h.uc.reg_read(UC_ARM64_REG_X0)),
            'instruction_count': h.steps, 'hardware_not_executed': True}


def run_still_geometry_fragment(livephoto=False, fov_type=3, corrected=False,
                                raw_width=4096, raw_height=3072, image_data=None):
    """Replay the coordinate-canvas branch observed in exported camera logs.

    Controlled calibration canvas: 8192x6144. No allocation or ISP calls occur.
    """
    from livephoto_geometry_patch import apply_to_emulator
    h = Harness(image_data)
    if corrected:
        apply_to_emulator(h)
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    for offset, value in [(0xd8, raw_width), (0xf8, raw_width), (0x100, raw_height),
                          (0x104, 65), (0x108, 49), (0x258, fov_type),
                          (0x290, 8192), (0x294, 6144)]:
        h.uc.mem_write(sp + offset, struct.pack('<I', value))
    h.uc.reg_write(UC_ARM64_REG_X21, raw_height)
    h.uc.mem_write(0x1262e904, struct.pack('<I', int(livephoto)))
    h.stops[0x760878] = 'projection_geometry_ready'
    h.run(0x760804)
    return {'calibration_canvas': list(struct.unpack('<II', h.uc.mem_read(sp + 0x290, 8))),
            'projection_canvas': list(struct.unpack('<II', h.uc.mem_read(sp + 0x2a8, 8))),
            'raw_dimensions': list(struct.unpack('<II', h.uc.mem_read(sp + 0x298, 8))),
            'fov_type': struct.unpack('<I', h.uc.mem_read(sp + 0x258, 4))[0],
            'fragment_only': True, 'hardware_not_executed': True}


def run_livephoto_enable_validation_fragment(narrow=1, corrected=False, image_data=None):
    """Run enable validation through the real support check to its write boundary.

    The old SetNarrow(0) call is recorded but has no simulated side effect,
    matching the rejection observed in the exported trial-Y logs.
    """
    from livephoto_geometry_patch import apply_to_emulator
    from unicorn.arm64_const import UC_ARM64_REG_X24
    h = Harness(image_data)
    if corrected:
        apply_to_emulator(h)
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.reg_write(UC_ARM64_REG_X24, 1)
    h.uc.mem_write(sp + 0x48, struct.pack('<II', 2, 0))
    h.uc.mem_write(sp + 0x5c, struct.pack('<IIIII', 1, 0, 12, 12, 0))
    result = {'narrow_clear_attempts': 0}
    def config(uc):
        key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) == (1, 12):
            data = struct.pack('<III', 2, 0, 0)
        elif (key, size) == (0x1c, 8):
            data = bytes([5, 0, 0, 0, narrow, 100, 0, 0])
        else:
            raise ValueError('Unexpected enable-fragment configuration read')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), data)
        return 0
    def clear(uc):
        result['narrow_clear_attempts'] += 1
        return 0
    def write(uc):
        key, size = uc.reg_read(UC_ARM64_REG_X0), uc.reg_read(UC_ARM64_REG_X2)
        if (key, size) != (0x16, 4):
            raise ValueError('Unexpected first enable write')
        result['livephoto_enable_value'] = uc.mem_read(uc.reg_read(UC_ARM64_REG_X1), 1)[0]
        h.outcome = 'livephoto_enable_write_requested'
        uc.emu_stop()
        return 0
    h.mocks = {0x2e41a0: config, 0x2e4380: config, 0x2e4ae0: write,
               0x36a340: clear, 0x2639a0: lambda uc: 0, 0x71b880: lambda uc: 0}
    h.stops[0x370740] = 'rejected_by_livephoto_support_check'
    h.run(0x37043c)
    result.update(outcome=h.outcome, fragment_only=True, hardware_not_executed=True)
    return result


def run_rawpiv_fov_fragment(narrow=0, configured_fov=5, use_effective_fov=False,
                            resolution_id=226, image_data=None):
    """Execute RawPiv file-list FOV selection and real table-based math.

    Configuration, context lookup, feature/debug flags and logging are controlled.
    Stops before exposure queries, file IO, ISP work or image capture.
    """
    h = Harness(image_data)
    record = CONTEXT + 0x1000
    h.uc.reg_write(UC_ARM64_REG_X20, record)
    for offset, value in [(0x18d02, resolution_id), (0x18d0c, configured_fov),
                          (0x18d12, 1)]:
        h.uc.mem_write(CONTEXT + offset, struct.pack('<H', value))
    if use_effective_fov:
        assert bytes(h.uc.mem_read(0x76c178, 4)) == bytes.fromhex('61185a79')
        # ldr w1,[x20,#0xdc]: use the effective FOV after narrow override.
        h.uc.mem_write(0x76c178, struct.pack('<I', 0xb9400000 | (0xdc // 4 << 10) | (20 << 5) | 1))
    def config(uc):
        if uc.reg_read(UC_ARM64_REG_X0) != 0x1c or uc.reg_read(UC_ARM64_REG_X2) != 8:
            raise ValueError('Unexpected RawPiv zoom configuration read')
        data = bytearray(8)
        struct.pack_into('<I', data, 0, configured_fov)
        data[4] = narrow
        struct.pack_into('<H', data, 5, 100)
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1), bytes(data))
        return 0
    h.mocks = {0x28e120: lambda uc: CONTEXT, 0x15c3420: lambda uc: CONTEXT,
               0x2e4380: config, 0x774d80: lambda uc: 0,
               0x2e7040: lambda uc: 2, 0x2e7160: lambda uc: CONTEXT,
               0x28ff60: lambda uc: 0, 0x2639a0: lambda uc: 0,
               0x71b880: lambda uc: 0, 0x726280: lambda uc: 0}
    h.stops[0x76c19c] = 'rawpiv_fov_and_distance_computed'
    h.run(0x76c10c)
    return {'effective_fov_type': struct.unpack('<I', h.uc.mem_read(record + 0xdc, 4))[0],
            'fov_degrees': struct.unpack('<d', h.uc.mem_read(record + 0xe8, 8))[0],
            'distance': struct.unpack('<d', h.uc.mem_read(record + 0xf0, 8))[0],
            'instruction_count': h.steps, 'fragment_only': True,
            'hardware_not_executed': True}


def run_livephoto_mode_switch_fragment():
    """Execute the real enable tail through its camera-mode write boundary.

    Start with normal single-photo mode and an accepted enable request. Earlier
    request checks and hardware restart are outside this bounded fragment.
    """
    from unicorn.arm64_const import UC_ARM64_REG_X24
    h = Harness()
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0x5c, struct.pack('<4I2H', 1, 0, 12, 12, 0, 0))
    h.uc.reg_write(UC_ARM64_REG_X24, 1)
    h.stops[0x2e4ae0] = 'camera_mode_write_requested'
    h.run(0x37047c)
    if h.uc.reg_read(UC_ARM64_REG_X0) != 0x12 or h.uc.reg_read(UC_ARM64_REG_X2) != 20:
        raise ValueError('Unexpected camera-mode write')
    data = bytes(h.uc.mem_read(h.uc.reg_read(UC_ARM64_REG_X1), 20))
    values = struct.unpack('<4I2H', data)
    return dict(zip(['mode', 'submode', 'origin_mode', 'actual_mode',
                     'preset_type', 'preset_offset'], values))


def main():
    for name, args, edit in [
        ('stock, Live Photo off', GateInputs(), False),
        ('stock, Live Photo on', GateInputs(livephoto=True), False),
        ('memory-only gate edit, Live Photo on', GateInputs(livephoto=True), True),
        ('gate edit, recording state 4', GateInputs(livephoto=True, record_state=4), True),
        ('gate edit, switch busy', GateInputs(livephoto=True, switch_busy=1), True),
    ]:
        result = run_gate(args, edit)
        print(f'{name}: {result["outcome"]} ({result["instruction_count"]} instructions)')
    print('Zoom forwarding, 200% configuration:', json.dumps(run_zoom_forward()))
    print('Live Photo capture-config rewrite:', json.dumps(run_livephoto_config()))
    print('Memory-only narrow preservation:', json.dumps(run_livephoto_config(preserve_narrow=True)))
    print('Video permission check with narrow:', json.dumps(run_video_zoom_gate(narrow=1)))
    print('Still request fragment with narrow:', json.dumps(run_still_request_fragment(narrow=1)))
    print('Initial Live Photo capture template:', json.dumps(run_profile_selection_fragment(31)))
    print('Only isolated routines ran; no full-camera or ISP simulation, no firmware files modified.')


if __name__ == '__main__':
    main()
