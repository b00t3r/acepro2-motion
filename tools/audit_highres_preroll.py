"""Compare one observed native Live Photo and one high-res still timeline.

These are separate captures, not an experiment combining the two modes.
"""
import json
import re
from livephoto_harness import ROOT

LOG = ROOT / 'analysis/full-resolution-baseline/decoded/20261029_15.log.txt'


def events(first, last, needles):
    result = {}
    for number, line in enumerate(LOG.read_text(errors='replace').splitlines(), 1):
        if not first <= number <= last:
            continue
        for name, needle in needles.items():
            if name not in result and needle in line:
                match = re.match(r'\[(\d+)\]', line)
                if match:
                    result[name] = {'line': number, 'tick_ms': int(match[1]), 'text': line}
    if set(result) != set(needles):
        raise ValueError('Missing evidence: ' + ', '.join(set(needles) - set(result)))
    return result


def audit():
    live = events(1200, 2350, {'prerecord': 'Start pre-recording by livephoto@1',
        'shutter': 'Get Param islivephoto = 1', 'mux_start': 'MuxerRec enable:1',
        'mux_stop': 'MuxerRec enable:0'})
    still = events(11850, 12300, {'parameters': 'PreMode = 0/95 CapMode = 33',
        'liveview_stopping': 'status:INSMEDIA_MODULE_STATUS_LIVEVIEW_STOPPING',
        'sensor_reconfigured': 'Config Mode: 33(VinID: 0)',
        'raw_ready': '[CapData] raw addr:',
        'liveview_restarting': 'status:INSMEDIA_MODULE_STATUS_LIVEVIEW_STARTING'})
    return dict(live_photo=live, high_resolution_still=still,
        stop_to_restart_requested_ms=still['liveview_restarting']['tick_ms']-still['liveview_stopping']['tick_ms'],
        limitations=['Separate real captures; no combined 50 MP and pre-recording experiment.',
          'The interval ends at restart request, not the first resumed video frame.',
          'The log does not show that pre-recorded samples survive the pipeline stop or produce a valid Google Motion Photo.'])


if __name__ == '__main__':
    report = audit()
    out = ROOT / 'analysis/motion-resolution-audit/highres-preroll-timeline.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
