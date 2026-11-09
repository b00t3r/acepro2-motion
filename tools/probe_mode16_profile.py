"""Counterfactual callback test, not a full mode-16 camera configuration."""
import json
import struct
from livephoto_harness import ROOT, run_still_sensor_selection
from probe_fullsensor_actual_callback import probe


def audit():
    edits={0xc18:struct.pack('<I',16),0x18800:struct.pack('<I',16),
           0x187f8:struct.pack('<HH',8192,6144)}
    image=(ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    return dict(callback_cases=[probe(31,42,True,n,edits) for n in (0,1)],
        later_narrow_fragment=[run_still_sensor_selection(narrow=n,sensor_mode=16,
            image_data=image,livephoto=True) for n in (0,1)],
        limitations=['Only three fields in a copied 4096x3072 profile were changed; all other geometry and buffers remain native to the smaller profile.',
                     'Configuration reads, frame lookup and camera services are mocked; no sensor, ISP or video is executed.',
                     'Mode-16 Bayer, physical I2C and full callback pipeline are not validated.',
                     'No firmware package or camera change.'])


if __name__=='__main__':
    result=audit();out=ROOT/'analysis/motion-resolution-audit/mode16-callback-probe.json'
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
