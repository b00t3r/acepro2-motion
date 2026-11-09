"""Read-only capture timing and native PureShot format-selection audit."""
import json
import re
import struct
from pathlib import Path

from livephoto_harness import Harness
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X27


def pureshot_format(narrow, sensor_config_byte=0, raw_width=4096,
                    image_data=None, livephoto=False):
    """Execute the format decision, stopping before allocation/model execution.

    Only the logged local inputs are reproduced. This cannot emulate colour
    processing, the sensor, or the AI model itself.
    """
    h = Harness(image_data)
    h.uc.mem_write(0x1262e904, struct.pack('<I', int(livephoto)))
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_write(sp + 0x170, struct.pack('<I', raw_width))
    h.uc.mem_write(sp + 0x10c, bytes([narrow]))
    h.uc.mem_write(sp + 0x13d, bytes([sensor_config_byte]))
    h.uc.reg_write(UC_ARM64_REG_X27, 256)
    h.stops.update({0x755cf4: 'ordinary_format', 0x756098: 'qbc_format'})
    h.run(0x755cb4)
    return {'narrow': narrow, 'sensor_config_byte': sensor_config_byte,
            'qbc': struct.unpack('<I', h.uc.mem_read(sp + 0x1b4, 4))[0],
            'hardware_executed': False, 'model_executed': False}


def capture_timings(path):
    lines = path.read_text(errors='replace').splitlines()
    current = None
    rows = []
    for i, line in enumerate(lines):
        time = re.match(r'\[(\d+)\]', line)
        if not time:
            continue
        t = int(time[1])
        if '<MwStillCap> Get Param SyncEncStart' in line:
            current = {'log': path.name, 'capture_start_ms': t}
        if current is None:
            continue
        name = re.search(r'\[(C:.*?\.jpg)\] file close, mux time (\d+) ms', line)
        if name:
            current.update(filename=name[1].rsplit('\\', 1)[-1],
                           jpeg_close_ms=t, jpeg_mux_ms=int(name[2]))
        if 'Pureshot Proc Cost Time:' in line:
            current['pureshot_ms'] = int(re.search(r'Cost Time: (\d+)', line)[1])
        if 'Save img[' in line:
            current['native_metadata_done_ms'] = t
        if 'Free metadata buffer' in line and 'native_metadata_done_ms' in current:
            current['post_metadata_interval_ms'] = t-current['native_metadata_done_ms']
        if 'cap sta:INS_APP_CAPTURE_STATUS_IDLE(0)' in line and 'filename' in current:
            current['ready_ms'] = t
            current['capture_to_idle_ms'] = t-current['capture_start_ms']
            rows.append(current)
            current = None
    return rows


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    output = root / 'analysis/zoom-colour-948'
    report = {'native_format_decision': [pureshot_format(n) for n in (0, 1)],
              'latest_capture_timings': capture_timings(output/'new-logs/decoded/20261029_20.log.txt'),
              'limitation': 'Post-metadata interval includes the injected copy and scheduling; no explicit payload timer exists.'}
    (output/'pipeline-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
