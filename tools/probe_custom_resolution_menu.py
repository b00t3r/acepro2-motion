"""Exercise the camera's native resolution menu objects in an isolated emulator.

This is an offline feasibility probe, not a firmware patch or a UI renderer.
The embedded UI's string ownership helpers are mocked; native list limits and
native property setters execute unchanged from the pinned stock image.
"""
import json
import struct

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30
from livephoto_harness import Harness, CONTEXT, RETURN, ROOT

LABEL_CLASS = 0x1a6a0e8  # constructor 0x538500
VALUE_CLASS = 0x1a69cd8  # constructor 0x538340
LABEL_SETTERS = (0x53f760, 0x53f7c0, 0x53f820, 0x53f880,
                 0x53f8e0, 0x53f940, 0x53f9a0)
VALUE_SETTERS = (0x53f260, 0x53f280, 0x53f2a0, 0x53f2c0,
                 0x53f2e0, 0x53f300, 0x53f320)
EXISTING_VALUES = (3, 2, 4, 1, 0, 5)
LABELS = ('9MP', '12.5MP', '7MP', '37MP', '50MP', '28.5MP', 'C 20 MP')


def run(entry, h, *args):
    for register, value in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1), args):
        h.uc.reg_write(register, value)
    h.uc.reg_write(UC_ARM64_REG_X30, RETURN)
    h.outcome = None
    h.run(entry)
    return h.uc.reg_read(UC_ARM64_REG_X0)


def probe(count=7, custom_value=6):
    if not 0 <= count <= 10:
        raise ValueError('Only valid native list sizes are exercised')
    if custom_value in EXISTING_VALUES:
        raise ValueError('The test value must not collide with an existing menu value')
    h = Harness()
    h.uc.mem_map(0x12749000, 0x1000)
    labels, values = CONTEXT, CONTEXT + 0x200
    for obj, cls in ((labels, LABEL_CLASS), (values, VALUE_CLASS)):
        h.uc.mem_write(obj, struct.pack('<Q', cls))
    # String comparison/retention depends on the live UI allocator and GC.
    # Model only ownership; the actual native setters and bounds still run.
    h.mocks[0x467bc0] = lambda uc: 1
    h.mocks[0x467f00] = lambda uc: uc.reg_read(UC_ARM64_REG_X0)
    run(0x5414a0, h, labels, count)
    run(0x5413a0, h, values, count)
    ptrs = []
    for i, text in enumerate(LABELS[:count]):
        ptr = CONTEXT + 0x1000 + i * 64
        if i == 6:
            # An uncompressed native string resource begins with two FFFF
            # halfwords. The real resource loader returns the indexed string.
            raw = CONTEXT + 0x1900
            descriptor = CONTEXT + 0x1800
            h.uc.mem_write(raw, b'\xff\xff\xff\xff' + (text + '\0').encode('utf-16le'))
            h.uc.mem_write(descriptor, struct.pack('<QH6x', raw, 2))
            ptr = run(0x467ca0, h, descriptor)
            if ptr != raw + 4:
                raise ValueError('Native resource loader rejected custom text')
        else:
            h.uc.mem_write(ptr, (text + '\0').encode('utf-16le'))
        ptrs.append(ptr)
        run(LABEL_SETTERS[i], h, labels, ptr)
        run(VALUE_SETTERS[i], h, values,
            (EXISTING_VALUES + (custom_value,))[i])
    label_count = struct.unpack('<I', h.uc.mem_read(labels + 0x20, 4))[0]
    value_count = struct.unpack('<I', h.uc.mem_read(values + 0x20, 4))[0]
    custom_label = (bytes(h.uc.mem_read(ptrs[6], len(LABELS[6]) * 2)).decode('utf-16le')
                    if count == 7 else None)
    label_slots = list(struct.unpack('<7Q', h.uc.mem_read(labels + 0x78, 56)))
    value_slots = list(struct.unpack('<7I', h.uc.mem_read(values + 0x50, 28)))
    return dict(requested_count=count, native_label_count=label_count,
                native_value_count=value_count, label_pointers=label_slots,
                expected_label_pointers=ptrs, menu_values=value_slots,
                native_label_capacity=run(0x538ee0, h, labels),
                native_value_capacity=run(0x538e80, h, values),
                custom_label=custom_label,
                custom_label_loader='native uncompressed resource' if count == 7 else None,
                gui_rendered=False, app_mapping_verified=False,
                still_capture_implemented=False)


if __name__ == '__main__':
    report = probe()
    assert report['native_label_count'] == report['native_value_count'] == 7
    assert report['label_pointers'] == report['expected_label_pointers']
    assert report['menu_values'] == list(EXISTING_VALUES) + [6]
    path = ROOT / 'analysis/motion-resolution-audit/custom-menu-probe.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
