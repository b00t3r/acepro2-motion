"""Inventory firmware sensor modes and static profiles for the motion goal.

This inventory is restricted to the known sensor-mode and resource tables;
it does not establish physical support, runtime selection or photo quality.
"""
import json
from collections import defaultdict
from audit_motion_resolution import read_modes, read_format
from livephoto_harness import ROOT, image


def audit():
    data = image()
    modes = read_modes(data)
    profiles = defaultdict(list)
    for i in range(60):
        row = read_format(data, i)
        profiles[row['sensor_mode']].append({k: row[k] for k in (
            'format_index', 'label', 'vin_window', 'configured_fps', 'has_memory_raw_node')})
    eligible = []
    for mode in modes:
        if mode['width'] * mode['height'] <= 4096 * 3072:
            continue
        if mode['nominal_fps'] is None or mode['nominal_fps'] < 24:
            continue
        eligible.append(dict(mode=mode['mode'], sensor_output=[mode['width'], mode['height']],
            source_rect=mode['source_rect'], nominal_fps=mode['nominal_fps'],
            bayer_code=mode['bayer_code'], output_bits=mode['output_bits'],
            profiles=profiles[mode['mode']]))
    return dict(sensor_modes_inspected=len(modes), resource_profiles_inspected=60,
        criterion='sensor output above 4096x3072 pixels and nominal sensor rate >=24 fps',
        eligible_sensor_modes=eligible,
        limitations=['Sensor output is not the same as saved photo resolution or quality.',
          'The profile list uses static sensor mode fields, not runtime selections or other mode switches.',
          'Nominal frame rates are unverified; sensor, ISP, motion capture, memory and encoder compatibility are not tested.',
          'Does not enumerate every possible custom profile, multi-frame processing technique or lower-resolution sensor strategy.'])


if __name__ == '__main__':
    out = ROOT / 'analysis/motion-resolution-audit/continuous-highres-inventory.json'
    report = audit()
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
