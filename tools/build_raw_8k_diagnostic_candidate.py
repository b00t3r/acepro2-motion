"""Package a marker-gated raw diagnostic for a controlled hardware trial.

This package has not been validated on a camera. Native logging context,
stack margin and sample timing remain unverified.
"""
import json
import lz4.frame
from build_raw_8k_diagnostic_offline import build,OUT
from build_highres_memory_candidate import DEST as SOURCE
from build_motion_candidate import sha,edit_frame
from build_usb_name_candidate import USB_OFFSETS,unpack_package,repack
from livephoto_harness import ROOT

SOURCE_SHA='519dfd45b163e53259acd6f6c0dc7c061b0c2d1f0d53d80ff47b43c1b4e84846'
DEST=OUT/'Insta360AcePro2_8K-Raw-Diagnostic_Trial-Q3.bin'


def package():
    report=build()
    source=SOURCE.read_bytes()
    if sha(source)!=SOURCE_SHA: raise ValueError('Unexpected source firmware package')
    package=unpack_package(source)
    decoded=lz4.frame.decompress(package['parts'][0]['payload'])
    if decoded!=(ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes():
        raise ValueError('Source image mismatch')
    after=bytearray((OUT/'main_threadx_OFFLINE_ONLY.bin').read_bytes())
    for offset in USB_OFFSETS:
        if after[offset:offset+18]!=b'Insta360 Ace Pro X': raise ValueError('Unexpected USB marker')
        after[offset:offset+18]=b'Insta360 Ace Pro r'
    package['parts'][0]['payload']=edit_frame(package['parts'][0]['payload'],bytes(after))
    result=repack(package); check=unpack_package(result)
    if len(result)!=len(source) or lz4.frame.decompress(check['parts'][0]['payload'])!=after:
        raise ValueError('Package roundtrip mismatch')
    if check['parts'][1:]!=unpack_package(source)['parts'][1:]:
        raise ValueError('Unrelated partitions changed')
    DEST.write_bytes(result)
    report['limitations']=[x for x in report['limitations'] if x != 'No hardware change, flashable package, or card staging.']
    report['limitations'].append('Update package has not been staged or run on a camera; marker recovery is verified only in emulation.')
    report.update(status='Candidate for a controlled marker-off-first hardware trial',
        package=str(DEST),sha256=sha(result),source_sha256=SOURCE_SHA,
        usb_marker='Insta360 Ace Pro r',hardware_tested=False,staged=False)
    (OUT/'package-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(package(),indent=2))
