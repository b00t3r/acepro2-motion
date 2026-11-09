"""Run the native raw-feed flag selector against copied profile data.

The profile getter is mocked; no full startup, encoder, allocation or camera
hardware is run. Selector state starts zero to isolate this particular path.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE
from livephoto_harness import BASE, CONTEXT, ROOT, Harness, image
from probe_rawfeed_buffer_sizing import probe


def select(index, view_override=None):
    d = image()
    start = FORMAT_BASE - 0x20 - BASE + index * FORMAT_STRIDE
    h = Harness()
    h.uc.mem_map(0x141e9000, 0xc6000)
    h.uc.mem_write(CONTEXT, d[start:start + 0x5000])
    count = struct.unpack('<I', bytes(h.uc.mem_read(CONTEXT + 0x4418, 4)))[0]
    if count > 8:
        raise ValueError('Unexpected view count')
    if view_override is not None:
        view, value = view_override
        if view >= count:
            raise ValueError('Invalid view')
        h.uc.mem_write(CONTEXT + 0x44ed + 0x104 * view, bytes([value]))
    values = [bytes(h.uc.mem_read(CONTEXT + 0x44ed + 0x104 * i, 1))[0] for i in range(count)]
    h.mocks[0x28e120] = lambda uc: CONTEXT
    h.run(0x154dac0)
    flag = h.uc.reg_read(UC_ARM64_REG_X0)
    return dict(profile=index, view_bytes=values, selected_flag=flag,
                hypothetical_full_sensor_sizing=probe(8192,6144,flag),
                mock='profile getter returns copied static template',
                global_state='zero initialized for this isolated test',
                camera_executed=False)


def audit():
    return dict(native_profiles=[select(i) for i in (16,26,31,42)],
                counterfactual=select(31,(2,4)),
                limitations=['The selector accepts cached global state on another branch; actual runtime call order and profile changes are not established.',
                             'Changing a view byte to 4 is a diagnostic counterfactual, not a safe patch; its other effects have not been traced.',
                             'The selector is also called from other native routines, including 0x31b49c, 0x77ac14, 0x77f41c and 0x781da0; changing its result may affect other behavior.',
                             'The 8192x6144 allocation result combines isolated firmware fragments; no complete pipeline or allocation was executed.',
                             'Static recording streams do not prove view-to-encoder routing or a 1080p motion photo.'])


if __name__ == '__main__':
    result = audit()
    (ROOT / 'analysis/motion-resolution-audit/rawfeed-selector.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
