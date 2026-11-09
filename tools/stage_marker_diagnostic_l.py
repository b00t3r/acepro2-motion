"""Stage marker-only Trial L on the verified camera running Trial K."""
import json
import subprocess
import sys
import stage_colour_trial as staging
from build_fullsensor_marker_diagnostic import OUT, DEST
from stage_motion_trial import VOLUME, require, checksum

EXPECTED = '53916802f24664705310862e7bd4ebeb9b29400d669200dd1514401e614c8a0b'


def main():
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                    '-p', 'test_marker_only_diagnostic.py'], check=True)
    require(checksum(DEST) == EXPECTED, 'Trial L hash mismatch')
    marker = VOLUME/'FULLSENSOR.ENABLE'
    require(marker.is_file() and not marker.is_symlink(), 'Expected existing marker file is missing')
    report_path = OUT/'build_report.json'
    report = json.loads(report_path.read_text())
    report.update(regression_tests_passed=2, package_integrity_verified=True)
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    staging.OUT, staging.DEST, staging.EXPECTED = OUT, DEST, EXPECTED
    staging.main(required_tests=2, previous_usb_name='Insta360 Ace Pro K',
                 next_usb_name='Insta360 Ace Pro L', trial='L (marker-only, both zooms)')


if __name__ == '__main__': main()
