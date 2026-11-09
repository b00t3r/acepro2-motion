"""Stage the validated Trial U on the identified camera currently running T."""
import stage_colour_trial as staging
from build_live_isp_candidate import OUT, DEST

if __name__ == '__main__':
    staging.OUT = OUT
    staging.DEST = DEST
    staging.EXPECTED = '3bcb12eb9fabd0c8f902a489d1f30d2f3a530904e4419f7b1b13dccd0f298060'
    staging.main(required_tests=6, previous_usb_name='Insta360 Ace Pro T',
                 next_usb_name='Insta360 Ace Pro U', trial='U')
