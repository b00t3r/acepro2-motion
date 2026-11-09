"""Controlled, isolated sizing and ring experiments; not a candidate patch.

No allocation, raw feed task, consumer, camera or encoder is executed. The
experiments emulate two separate fragments with in-memory edits, not a pipeline.
"""
import json
from livephoto_harness import ROOT
from probe_rawfeed_buffer_sizing import probe as size
from probe_rawfeed_ring_index import probe as ring
from probe_rawfeed_timelapse_effect import probe as interval


def audit():
    modified_size=size(8192,6144,0,force_five=True)
    counters=(0,1,4,5,6,31,32,127)
    ring_cases=[ring(0,n,force_five=True) for n in counters]
    return dict(sizing=modified_size, ring_cases=ring_cases,
        interval_case=interval(0,2),
        remaining_known_ring_selector_reads=['0x1548eb8','0x1548f0c','0x154ccec',
            '0x154cd18','0x154d418','0x154d46c','0x154dee4','0x154df10'],
        limitations=['These are separate CPU fragments with controlled state; no concurrency or buffer ownership is simulated.',
            'The listed ring-selector reads are not changed; the actual pipeline would remain unsafe.',
            'Other selector uses include raw-feed interval and task behavior; changing only these two instructions is not a safe camera patch.',
            'Selector, interval setter, recording stream and sensor/ISP have not been executed together.',
            'No camera change and no firmware image produced.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-coordinated-fragments.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
