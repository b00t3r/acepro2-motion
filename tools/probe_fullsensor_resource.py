"""Compare a full-sensor template selection with Live Photo timing offline.

Changes are confined to an emulator image. No candidate or camera write is
produced; fps values are configuration fields, not measured frame rates.
"""
import json
import struct

from audit_motion_resolution import read_format
from livephoto_harness import BASE, ROOT, image, run_livephoto_config, run_profile_selection_fragment

TABLE = 0x194ffd8
ROW_BYTES = 124
ROW = 194


def probe():
    original = (ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    trial = bytearray(original)
    row = TABLE - BASE + ROW * ROW_BYTES
    fields = struct.unpack_from('<12I', trial, row)
    if fields[:11] != (2, 2, 2, 3840, 2880, 3840, 2880, 30, 227, 30, 30):
        raise ValueError('Unexpected 4:3 Live Photo resource descriptor')
    # Scope is intentionally just this row in the emulator copy. Native
    # processing overrides and stream topology are not changed or validated.
    struct.pack_into('<II', trial, row + 36, 49, 49)
    trial = bytes(trial)
    cases = []
    for resource in (226, 227):
        for narrow in (0, 1):
            before = run_livephoto_config(resolution_id=resource, narrow=narrow,
                                          image_data=original, include_encoding=True)
            after = run_livephoto_config(resolution_id=resource, narrow=narrow,
                                         image_data=trial, include_encoding=True)
            cases.append(dict(resource=resource, narrow=narrow,
                              before_ids=before['resource_ids'], after_ids=after['resource_ids'],
                              live_fps_numerator=after['fps_numerator'],
                              live_fps_denominator=after['fps_denominator'],
                              live_frame_size=after['dimensions']))
    template = read_format(image(), 42)
    return dict(cases=cases, selected_template=run_profile_selection_fragment(49),
                template_frame_rate=template['frame_rate_words'],
                timing_difference='The 4:3 Live Photo resource requests 30000/1001 fps, while template 42 configures its sensor input at 5000/1000 fps. The template also contains 30000/1001 values elsewhere; rate conversion, buffering and output behavior remain unverified.',
                rawpiv_sensor_override='A separate burst-photo callback forces mode 36 or 27 in isolation. Native capture 49 selects a different callback, so this experiment does not establish its actual sensor selection.',
                flashable_candidate_created=False, hardware_executed=False)


if __name__ == '__main__':
    result = probe()
    output = ROOT / 'analysis/motion-resolution-audit/fullsensor-resource-mismatch.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
