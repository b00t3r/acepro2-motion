"""Run the native interval setter with the selector and logging mocked.

This does not execute frame capture, recording, the caller, or sensor hardware.
"""
import json
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1
from livephoto_harness import Harness, ROOT


def probe(selector, requested_interval, short_rec=0):
    h = Harness()
    h.uc.mem_map(0x128e1000, 0x1000)
    h.mocks[0x154dac0] = lambda uc: selector
    h.mocks[0x2639a0] = lambda uc: 0
    h.mocks[0x71b880] = lambda uc: 0
    h.uc.reg_write(UC_ARM64_REG_X0, requested_interval)
    h.uc.reg_write(UC_ARM64_REG_X1, short_rec)
    h.run(0x781d80)
    interval, recorded_short = bytes(h.uc.mem_read(0x128e1338, 2))
    return dict(mocked_selector=selector, requested_interval=requested_interval,
                stored_interval=interval, stored_short_rec=recorded_short,
                mocked_calls=[hex(x) for x in h.calls], camera_executed=False)


def audit():
    return dict(cases=[probe(s, n) for s in (0,1) for n in (0,2,5,6)],
        firmware_strings=['In 8k timelapse mode, so change interval from %u to %u',
                          'set force keep interval:%d,short_rec:%d'],
        limitations=['Only the interval setter was executed, with selector and logging mocked.',
                     'Whether this setter is called by the proposed configuration and its effect on encoded frames have not been established.',
                     'The five-buffer selector is associated with timelapse logic; that association alone does not prove smooth video impossible.'])


if __name__ == '__main__':
    result=audit()
    (ROOT/'analysis/motion-resolution-audit/rawfeed-timelapse-effect.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
