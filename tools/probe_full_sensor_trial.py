"""Gather the separate full-sensor software probes without making firmware.

Format 42's table is 5 fps. Its high-resolution readout, video concurrency,
image processing and final output remain unverified on camera hardware.
"""
import json

from audit_motion_resolution import read_format
from livephoto_harness import ROOT, image
from probe_rawpiv_resolution import probe as rawpiv
from probe_still_output_geometry import probe as geometry
from probe_still_processing_tiles import probe as tiles
from probe_sensor_mode_info import probe as sensor_info
from audit_capture_pipeline import pureshot_format


def audit():
    template = read_format(image(), 42)
    if (template['sensor_mode'], template['vin_window'], template['configured_fps']) != (53, [8192, 6144], 5.0):
        raise ValueError('Expected native full-sensor template changed')
    return dict(native_full_template=template,
                native_sensor_mode_info=[sensor_info(n) for n in (16, 33, 53)],
                native_selector_experiments=[rawpiv(42, narrow=n, experimental_full_mode=53) for n in (0, 1)],
                special_state_override_experiment=rawpiv(42, experimental_full_mode=53, special_mode_flag=1),
                configured_output_experiment=geometry(),
                processing_width_experiments=[tiles(w) for w in (4096, 8192)],
                full_width_pureshot_selection=[pureshot_format(narrow=n, raw_width=8192,
                    image_data=(ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes(),
                    livephoto=True) for n in (0, 1)],
                warnings=['The native full-sensor template is 5 fps.',
                          'The RawPiv selector experiment is counterfactual: native capture ID 49 uses a different callback, whose complete behavior has not been established.',
                          'The separately described 30 fps full-sensor mode uses a different Bayer code than the hardware-tested ordinary 50 MP mode; neither its Live Photo pipeline nor colour is verified.',
                          'Selector edits are unscoped emulator changes, not firmware patches.',
                          'In the burst callback, a separate native special-mode flag can force sensor mode 36 while full raw dimensions remain set. It is not established that capture ID 49 executes this branch.',
                          'DSP, ISP, buffer ownership, output pixels, zoom and continuous motion capture remain unvalidated.',
                          'A full-width input needs a different processing configuration from the installed Live Photo setup.'],
                flashable_candidate_created=False, hardware_executed=False)


if __name__ == '__main__':
    report = audit()
    output = ROOT / 'analysis/motion-resolution-audit/full-sensor-software-probe.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'native_full_sensor_template_fps': report['native_full_template']['configured_fps'],
                      'warnings': report['warnings'],
                      'flashable_candidate_created': False}, indent=2))
