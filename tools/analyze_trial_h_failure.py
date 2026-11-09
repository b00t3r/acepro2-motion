"""Extract comparable evidence from the saved Trial H crash and baseline logs."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILED = ROOT/'analysis/trial-h-bootloop/logs/decoded/20261030_08.log.txt'
BASELINES = [ROOT/'analysis/trial-x-memory-hardware/logs/decoded/20261030_02.txt',
             ROOT/'analysis/trial-x-memory-hardware/logs/decoded/20261030_03.log.txt']


def collect(lines, expression, offset=0):
    regex = re.compile(expression)
    return [dict(line=i+1+offset, text=s) for i, s in enumerate(lines) if regex.search(s)]


def main():
    lines = FAILED.read_text(errors='replace').splitlines()
    start = next(i for i,s in enumerate(lines) if 'marker status 1' in s)
    end = next(i for i in range(start+1,len(lines)) if '[AIP3] Log Init Success' in lines[i])
    trial = lines[start:end]
    patterns = dict(selection=r'new cap cfg:.*cap_id=\[49:49\]',
        budget=r'GetNeededDspWorkSize.*FormatId 42', sensor=r'Config Mode: 53',
        timing=r'frame_rate = 0\.000|Main cache_num:.*fps:5',
        stabilization_errors=r'orient_box_filter sldw size = -2|Flowstate_DynamicFovSet failed|AmbaIK_SetWarpInfo:0x1100008',
        raw_buffer=r'RawBufferTotalSize|RawBuffTotalInit.*buffer size OK',
        last_retained=r'Calib update start|Calibration ca info|VinSelectBits')
    events = {key:collect(trial,regex,start) for key,regex in patterns.items()}
    for key in patterns:
        if not events[key]: raise ValueError('Expected trial evidence missing: '+key)
    baselines=[]
    for path in BASELINES:
        contents=path.read_text(errors='replace').splitlines()
        baselines.append(dict(path=str(path.relative_to(ROOT)),
            zero_rate_count=len(collect(contents,patterns['timing'].split('|')[0])),
            stabilization_error_count=len(collect(contents,patterns['stabilization_errors']))))
    result=dict(failed_log=str(FAILED.relative_to(ROOT)), start_line=start+1, next_boot_line=end+1,
        events=events, working_baselines=baselines,
        conclusions=['Hardware selected sensor mode 53 and format 42; this is not yet proof of a successful photo.',
                     'The full-sensor raw plus CE buffer reports a successful 629145600-byte allocation; that does not rule out other memory failures.',
                     'Actual format 42 DSP budget was 0x697ffc00; prior isolated emulator prediction of 0x74000000 did not match this hardware path.',
                     '0 fps occurs elsewhere in the saved logs; by itself it is not proof of failure.',
                     'Stabilization errors are present before reset and absent in these two working baseline logs, but a causal link is unproven.',
                     'The log ends during calibration and resumes at boot. A definitive reset or crash cause is not retained.',
                     'The saved DSP log has timeouts but cannot yet be reliably correlated to the transition.'],
        camera_changed=False)
    out=ROOT/'analysis/trial-h-bootloop/detailed-diagnosis.json'
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'start_line':start+1,'next_boot_line':end+1,'working_baselines':baselines,
                      'conclusions':result['conclusions']},indent=2))


if __name__=='__main__': main()
