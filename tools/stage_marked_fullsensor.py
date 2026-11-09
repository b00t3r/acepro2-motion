"""Stage Trial H only with the experimental activation marker disabled."""
import json
import subprocess
import sys
import stage_colour_trial as staging
from build_marked_fullsensor_candidate import OUT, DEST
from stage_motion_trial import VOLUME, require, checksum

EXPECTED = '7ac241a2688366ac3e61e85b7aebb9af903fbbd5a104310e7a77185005138637'


def main():
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                    '-p', 'test_marked_fullsensor_candidate.py'], check=True)
    require(checksum(DEST) == EXPECTED, 'Trial H hash mismatch')
    enabled, disabled = VOLUME/'FULLSENSOR.ENABLE', VOLUME/'FULLSENSOR.DISABLED'
    require(not enabled.exists() and not enabled.is_symlink(), 'Experimental marker is enabled')
    require(disabled.is_file() and not disabled.is_symlink(), 'Missing disabled marker')
    require(disabled.read_bytes() == b'Marker-only diagnostic; no high-resolution mode enabled.\n',
            'Unexpected disabled marker contents')
    report_path = OUT/'build_report.json'
    report = json.loads(report_path.read_text())
    report.update(regression_tests_passed=2, package_integrity_verified=True,
                  marker_disabled_at_staging=True)
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    staging.OUT, staging.DEST, staging.EXPECTED = OUT, DEST, EXPECTED
    staging.main(required_tests=2, previous_usb_name='Insta360 Ace Pro L',
                 next_usb_name='Insta360 Ace Pro H', trial='H (full-sensor diagnostic, marker disabled)')


if __name__=='__main__': main()
