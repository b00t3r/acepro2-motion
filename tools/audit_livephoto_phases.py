"""Read-only phase measurements for the hardware-tested W captures.

Separates existing PureShot/video overlap from the record-stop barrier and
later still conversion. Logs are observations, not proof of DSP concurrency.
"""
import json
import re
from pathlib import Path
from audit_capture_pipeline import capture_timings

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT/'analysis/trial-w-hardware/logs/decoded/20261029_48.log.txt'


def phases(log=LOG):
    records=[]
    for line in log.read_text(errors='replace').splitlines():
        match=re.match(r'\[(\d+)\]',line)
        if match: records.append((int(match[1]),line))
    rows=[]
    for capture in capture_timings(log):
        if not capture['filename'].startswith('LIV_20261029_2100'): continue
        start,end=capture['capture_start_ms'],capture['ready_ms']
        current=[(t,line) for t,line in records if start<=t<=end]
        def first(text):
            return next(t for t,line in current if text in line)
        pure=first('Pureshot Proc Cost Time:')
        stop=first('<INS_LIVEPHOTO> rec_stop:')
        proc=first('<SvcStlProc> ######### Proc Msgq Recv Msg')
        yuv=first('<SvcStlProc> main yuv done,')
        enc=next(t for t,line in current if '<SvcStlEnc> [SvcStillEnc_TaskEntry]' in line and 'view 0x0,' in line)
        rows.append(dict(filename=capture['filename'],capture_start_ms=start,
                         pureshot_done_ms=pure,record_stop_request_ms=stop,
                         still_processing_start_ms=proc,main_yuv_ready_ms=yuv,
                         jpeg_encoder_start_ms=enc,ready_ms=end,
                         pureshot_already_overlaps_video=pure<stop,
                         wait_after_pureshot_ms=proc-pure,
                         raw_to_main_yuv_ms=yuv-proc,
                         yuv_to_encoder_ms=enc-yuv,
                         encoder_to_ready_ms=end-enc,
                         capture_to_idle_ms=end-start))
    return rows


def main():
    report=dict(captures=phases(),native_record_stop_wait='0x3008e0, called from 0x755c30',
                following_metadata_setup='0x8bcc80(0,0), called from 0x755c3c',
                shared_encoder_buffer=dict(video_start='0xd0525380',video_size=536805376,
                                           jpeg_start='0xd0525380',jpeg_size=0x1fff8000,
                                           overlap_confirmed=True),
                private_still_buffers=dict(raw='0xf3816e00',ce='0xf5016e00',
                                           y='0xf5616e00',uv='0xf6216e00'),
                candidate_created=False,camera_changed=False,
                conclusion='PureShot already overlaps video. Do not remove the record-stop wait without a later encoder barrier and a proven metadata/buffer lifecycle.',
                limits='Moving private YUV work earlier is a candidate for further study, not proven safe by addresses alone; no ISP concurrency is emulated.')
    dest=ROOT/'analysis/trial-w-hardware/phase-audit.json'
    dest.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
