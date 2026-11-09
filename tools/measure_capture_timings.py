"""Measure native capture/save log intervals across ordered, decoded log files.

Pass logs in capture order, including adjacent files when one capture spans
the logger's file rotation. Post-metadata time includes copying and scheduling;
it is not a direct timer around the injected function.
"""
import argparse
import json
import tempfile
from pathlib import Path
from audit_capture_pipeline import capture_timings


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('logs',type=Path,nargs='+')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--capture',action='append',default=[])
    args=p.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        combined=Path(folder)/'ordered-logs.txt'
        combined.write_text('\n'.join(f.read_text(errors='replace') for f in args.logs))
        rows=capture_timings(combined)
    if args.capture:
        rows=[r for r in rows if any(c in r.get('filename','') for c in args.capture)]
    for r in rows:r.pop('log',None)
    report=dict(source_logs=[str(f.resolve()) for f in args.logs],captures=rows,
        limitation='Post-metadata interval includes packaging and scheduling; log timestamps measure elapsed capture state, not button response.')
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
