"""Explore an in-memory-only sizing edit; this is not a firmware candidate."""
import json
from livephoto_harness import ROOT
from probe_rawfeed_buffer_sizing import probe as sizing
from probe_rawfeed_timelapse_effect import probe as interval


def audit():
    return dict(native=sizing(8192, 6144, 0),
        experimental=sizing(8192, 6144, 0, force_five=True),
        interval_setter_for_selector_zero=interval(0, 2),
        interval_setter_for_selector_one=interval(1, 2),
        static_ring_observation='At 0x154c67c-0x154c6bc, the native raw-feed code uses the same flag to choose modulo 32 or 5 and multiplies the index by raw-frame size to form a buffer address. A sizing-only edit leaves this selection unchanged.',
        limitations=['Sizing and interval setter were run separately; selector input and camera state are controlled.',
            'A sizing-only edit can leave 32-slot addressing paired with five-frame allocation; do not deploy it. The observed indexing fragment and its full runtime path have not been executed.',
            'No complete pipeline, frame acquisition, encoding or actual camera was executed.',
            'The experiment does not establish that the interval setter runs during Live Photo.',
            'No flashable firmware created.'])


if __name__ == '__main__':
    r=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-decoupling.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
