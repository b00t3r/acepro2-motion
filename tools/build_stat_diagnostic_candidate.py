"""Package read-only stat diagnostic; never stages it."""
import json
import lz4.frame
from build_stat_diagnostic_offline import build,OUT,SOURCE,SOURCE_SHA
from build_motion_candidate import edit_frame,sha
from build_usb_name_candidate import USB_OFFSETS,unpack_package,repack

DEST=OUT/'Insta360AcePro2_FS-Status-Diagnostic_Trial-U3.bin'


def package():
    report=build();source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA:raise ValueError('Unexpected source')
    model=unpack_package(source);original=unpack_package(source)
    after=bytearray((OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes())
    for off in USB_OFFSETS:
        if after[off:off+18]!=b'Insta360 Ace Pro t':raise ValueError('Unexpected USB identity')
        after[off:off+18]=b'Insta360 Ace Pro u'
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    result=repack(model);check=unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(check['parts'][0]['payload'])!=after:
        raise ValueError('Package roundtrip mismatch')
    if check['parts'][1:]!=original['parts'][1:]:raise ValueError('Other partitions changed')
    DEST.write_bytes(result)
    report.update(package=str(DEST),sha256=sha(result),usb_name='Insta360 Ace Pro u',
        status='Read-only marker-gated candidate; not hardware tested or staged.',hardware_tested=False,staged=False)
    (OUT/'package-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(package(),indent=2))
