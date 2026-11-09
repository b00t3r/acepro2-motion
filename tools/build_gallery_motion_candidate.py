"""Package the gallery-compatible builder without removing any camera media."""
import json
import lz4.frame
from build_gallery_motion_offline import build, OUT, SOURCE, SOURCE_SHA
from build_motion_candidate import edit_frame, sha
from build_usb_name_candidate import ROOT, USB_OFFSETS, unpack_package, repack

DEST=OUT/'Insta360AcePro2_Gallery-Motion_Builder_Trial-T3.bin'


def package():
    report=build();source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Unexpected source package')
    model=unpack_package(source);original=unpack_package(source)
    after=bytearray((OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes())
    for offset in USB_OFFSETS:
        if after[offset:offset+18]!=b'Insta360 Ace Pro s': raise ValueError('Unexpected USB identity')
        after[offset:offset+18]=b'Insta360 Ace Pro t'
    model['parts'][0]['payload']=edit_frame(model['parts'][0]['payload'],bytes(after))
    result=repack(model);check=unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(check['parts'][0]['payload'])!=after:
        raise ValueError('Package roundtrip mismatch')
    if check['parts'][1:]!=original['parts'][1:]: raise ValueError('Other partitions changed')
    DEST.write_bytes(result)
    report.update(package=str(DEST),sha256=sha(result),usb_name='Insta360 Ace Pro t',
                  status='Candidate for hardware verification; source files retained.',
                  hardware_tested=False,staged=False)
    report['limitations']=[x for x in report['limitations'] if 'No flashable package' not in x]
    (OUT/'package-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(package(),indent=2))
