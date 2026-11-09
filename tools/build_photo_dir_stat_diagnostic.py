"""Make a narrow variant of the U3 stat diagnostic; never stage the file."""
import json
from pathlib import Path
import lz4.frame
from build_motion_candidate import sha,edit_frame
from build_usb_name_candidate import ROOT,USB_OFFSETS,unpack_package,repack

SOURCE=ROOT/'builds/offline-stat-diagnostic/Insta360AcePro2_FS-Status-Diagnostic_Trial-U3.bin'
OUT=ROOT/'builds/offline-photo-dir-stat'
DEST=OUT/'Insta360AcePro2_Photo-Directory-Status_Trial-X3.bin'
OLD=b'C:\\CODEX_STAT_MISSING_4271.TST'
NEW=b'C:\\DCIM\\Camera01\\CXMISS001.TST'
SOURCE_SHA='115871ce666a059544c8b14e45a34364aa9f1c0b42174c423105fa62da3e3059'

def build():
    data=SOURCE.read_bytes()
    if sha(data)!=SOURCE_SHA:raise ValueError('Unexpected U3 firmware')
    model=unpack_package(data);original=unpack_package(data)
    before=lz4.frame.decompress(model['parts'][0]['payload']);after=bytearray(before)
    if len(OLD)!=len(NEW) or before.count(OLD)!=1:raise ValueError('Path mismatch')
    offset=before.index(OLD);after[offset:offset+len(OLD)]=NEW
    for off in USB_OFFSETS:
        if after[off:off+18]!=b'Insta360 Ace Pro u':raise ValueError('Unexpected U3 USB name')
        after[off:off+18]=b'Insta360 Ace Pro x'
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    result=repack(model);check=unpack_package(result)
    if len(result)!=len(data) or lz4.frame.decompress(check['parts'][0]['payload'])!=after:raise ValueError('Roundtrip mismatch')
    if check['parts'][1:]!=original['parts'][1:]:raise ValueError('Other partitions changed')
    OUT.mkdir(parents=True,exist_ok=True);DEST.write_bytes(result)
    (OUT/'main_threadx_OFFLINE_ONLY.bin').write_bytes(after)
    report={'source_sha256':SOURCE_SHA,'sha256':sha(result),'path_offset':offset,'path':NEW.decode(),
            'usb_name':'Insta360 Ace Pro x','status':'Offline only; marker disabled for first boot; not staged'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':print(json.dumps(build(),indent=2))
