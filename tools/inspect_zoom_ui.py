#!/usr/bin/env python3
"""Execute isolated UI resource decoding and zoom-disable checks; no camera IO."""
import struct

from livephoto_harness import Harness, CONTEXT, ROOT, image
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X8, UC_ARM64_REG_X30
from livephoto_harness import RETURN


def warning_resource(resource_address=0x19c4d40, language=1):
    h = Harness()
    h.uc.mem_map(0x12749000, 0x1000)
    h.uc.mem_write(0x12749c40, struct.pack('<Q', CONTEXT + 0x10000))
    resources = (ROOT / 'analysis/extracted/ewres.bin').read_bytes()
    data = image()
    table, count = struct.unpack_from('<QI', data, resource_address - 0x50000)
    selected = None
    for i in range(count):
        lang, pointer, index = struct.unpack_from('<I4xQH', data, table - 0x50000 + i * 24)
        if lang == language:
            selected = pointer, index
            break
    if selected is None:
        raise ValueError('Language not found in warning resource')
    pointer, index = selected
    # Resource mapping verified by decoding its actual localized text.
    offset = pointer - 0x3ea4f40
    if not 0 <= offset < len(resources) - 4:
        raise ValueError('Resource pointer outside ewres.bin')
    size = struct.unpack_from('<I', resources, offset)[0]
    if not 0 < size < 0x4000:
        raise ValueError('Unexpected resource chunk length')
    h.uc.mem_write(CONTEXT + 0x1000, resources[offset + 4:offset + 0x4000])
    h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT + 0x1000)
    h.uc.reg_write(UC_ARM64_REG_X1, CONTEXT + 0x8000)
    h.run(0x4650c0, max_instructions=200000)
    decoded = bytes(h.uc.mem_read(CONTEXT + 0x8000, size))
    # Ew string resource stores a halfword offset into the decoded chunk.
    return decoded[index * 2:].decode('utf-16le').split('\0')[0]


def livephoto_disable_reason(narrow=0, ratio=1.0, selected_mode=3,
                             capability_value=0, error_status=0,
                             bypass_zoom_restriction=False, image_data=None,
                             refresh_control=False, press_button=False):
    """Execute inverse Live Photo UI check, retaining capability/error guards."""
    h = Harness(image_data)
    main, options, control = CONTEXT + 0x1000, CONTEXT + 0x4000, CONTEXT + 0x8000
    for offset, value in [(0x3bc, narrow), (0x54c, error_status), (0x550, 2)]:
        h.uc.mem_write(main + offset, struct.pack('<I', value))
    h.uc.mem_write(main + 0x168, struct.pack('<f', ratio))
    h.uc.mem_write(options + 0x15b8, struct.pack('<I', selected_mode))
    def lookup(uc):
        descriptor = uc.reg_read(UC_ARM64_REG_X0)
        if descriptor == 0x1a68618:
            return main
        if descriptor == 0x1a6bf40:
            return options
        if descriptor in [0x1a6aca0, 0x1a6ac88]:
            return control
        raise ValueError(f'Unexpected GUI object {descriptor:x}')
    h.mocks = {0x4634c0: lookup, 0x5667a0: lambda uc: capability_value}
    if bypass_zoom_restriction:
        assert bytes(h.uc.mem_read(0x55b034, 4)) == bytes.fromhex('e10314aa')
        h.uc.mem_write(0x55b034, bytes.fromhex('f3ffff17'))
    if refresh_control:
        def binding(uc):
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X8), bytes(24))
            return 0
        h.mocks.update({0x4645e0: binding, 0x466920: lambda uc: 0})
        h.uc.reg_write(UC_ARM64_REG_X0, control)
        h.run(0x55b080)
        result = {'reason': struct.unpack('<I', h.uc.mem_read(control + 0x10d4, 4))[0],
                  'disabled_flag': h.uc.mem_read(control + 0x1104, 1)[0]}
    else:
        h.run(0x55af20)
        result = {'reason': h.uc.reg_read(UC_ARM64_REG_X0)}
    if press_button:
        if not refresh_control:
            raise ValueError('Refresh the actual control before testing its button')
        h.outcome = None
        h.uc.reg_write(UC_ARM64_REG_X30, RETURN)
        h.stops.update({0x558da0: 'livephoto_switch_request_boundary',
                        0x468b20: 'warning_resource_boundary',
                        0x50ff20: 'capability_popup_boundary'})
        h.run(0x5db140)
        result['press_outcome'] = h.outcome
    return result


def zoom_disable_reason(model_state=1, selected_mode=3, feature_available=True,
                        guard_a=0, guard_b=0, lens_value=0, allow_model_state_one=False,
                        allow_both_model_states=False, refresh_control=False, image_data=None,
                        press_button=False, press_entry=0x5beb40):
    h = Harness(image_data)
    main, options, control = CONTEXT + 0x1000, CONTEXT + 0x4000, CONTEXT + 0x8000
    for offset, value in [(0x450, int(feature_available)), (0x550, model_state)]:
        h.uc.mem_write(main + offset, struct.pack('<I', value))
    for offset, value in [(0x15b8, selected_mode), (0x164c, guard_a),
                          (0x1644, guard_b), (0x1678, lens_value)]:
        h.uc.mem_write(options + offset, struct.pack('<I', value))

    def lookup(uc):
        descriptor = uc.reg_read(UC_ARM64_REG_X0)
        if descriptor == 0x1a68618:
            return main
        if descriptor == 0x1a6bf40:
            return options
        if descriptor in [0x1a6aca0, 0x1a6ac88]:
            return control
        raise ValueError(f'Unexpected GUI object {descriptor:x}')

    h.mocks = {0x4634c0: lookup}
    if allow_model_state_one and allow_both_model_states:
        raise ValueError('Select one UI edit')
    if allow_model_state_one:
        if bytes(h.uc.mem_read(0x55ae20, 4)) != bytes.fromhex('40feff54'):
            raise ValueError('Unexpected UI state-one branch')
        # Preserve state two, other disable reasons, and all UI state fields.
        h.uc.mem_write(0x55ae20, bytes.fromhex('1f2003d5'))
    if allow_both_model_states:
        if bytes(h.uc.mem_read(0x55adec, 4)) != bytes.fromhex('ff0e0071'):
            raise ValueError('Unexpected UI selected-mode comparison')
        # Skip only warning 16; continue checking accessory restrictions.
        h.uc.mem_write(0x55adec, struct.pack('<I', 0x1400000e))
    if refresh_control:
        def binding(uc):
            uc.mem_write(uc.reg_read(UC_ARM64_REG_X8), bytes(24))
            return 0
        h.mocks.update({0x4645e0: binding, 0x466920: lambda uc: 0})
        h.uc.reg_write(UC_ARM64_REG_X0, control)
        # Run the real evaluator, reason setter, and availability-flag update.
        h.run(0x55ae60)
        result = {'reason': struct.unpack('<I', h.uc.mem_read(control + 0x10c4, 4))[0],
                  'availability_flag': h.uc.mem_read(control + 0x10ed, 1)[0],
                  'model_state_after': struct.unpack('<I', h.uc.mem_read(main + 0x550, 4))[0]}
        if press_button:
            if press_entry not in [0x5beb40, 0x5b7660, 0x555100]:
                raise ValueError('Unknown warning path')
            h.stops.update({0x468b20: 'warning_resource_requested',
                            0x559760: 'next_ui_action_boundary',
                            0x5596e0: 'next_ui_action_boundary',
                            0x555164: 'next_ui_action_boundary'})
            h.outcome = None
            h.uc.reg_write(UC_ARM64_REG_X0, CONTEXT + 0xc000)
            h.uc.reg_write(UC_ARM64_REG_X30, RETURN)
            # The real widget callback and its real press handler execute.
            # Stop before any UI action is treated as an app/capture success.
            h.run(press_entry)
            result['press_outcome'] = h.outcome
            if h.outcome == 'warning_resource_requested':
                result['warning_resource'] = h.uc.reg_read(UC_ARM64_REG_X0)
        return result
    h.run(0x55ad40)
    return h.uc.reg_read(UC_ARM64_REG_X0)


def zoom_toggle_notification(current_narrow=0, supported_option_count=2):
    """Run the native zoom toggle and property setter to its notification.

    The GUI object lookup, option-list count, notification queue, and resource
    formatting are explicit mocks. No image-processing result is implied.
    """
    h = Harness()
    main, panel = CONTEXT + 0x1000, CONTEXT + 0x10000
    h.uc.mem_write(main + 0xdc, struct.pack('<I', 3))
    h.uc.mem_write(main + 0x3bc, struct.pack('<I', current_narrow))
    h.uc.mem_write(main + 0x168, struct.pack('<f', 1.0))
    notifications = []

    def lookup(uc):
        address = uc.reg_read(UC_ARM64_REG_X0)
        if address == 0x1a68618:
            return main
        if address == 0x1a6bf28:
            return panel
        raise ValueError(f'Unexpected toggle object {address:x}')

    def notify(uc):
        notifications.append({'device_id': uc.reg_read(UC_ARM64_REG_X0),
                              'narrow': struct.unpack('<I', uc.mem_read(main + 0x3bc, 4))[0]})
        return 0

    def binding(uc):
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X8), bytes(24))
        return 0

    h.mocks = {0x4634c0: lookup, 0x53b900: lambda uc: supported_option_count,
               0x4d49a0: notify, 0x467ca0: lambda uc: 0, 0x4615c0: lambda uc: 0,
               0x4645e0: binding, 0x466920: lambda uc: 0}
    h.run(0x556be0)
    return notifications


if __name__ == '__main__':
    for lang in [1, 2, 3]:
        print('Warning text, language', lang, ':', repr(warning_resource(language=lang)))
    for state in [0, 1, 2]:
        print('Model state', state, 'stock disable reason:', zoom_disable_reason(state))
