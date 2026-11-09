"""Stage validated Trial T on the identified camera running Trial S."""
import stage_colour_trial as staging
from build_live_capmode_candidate import OUT, DEST

if __name__ == '__main__':
    staging.OUT = OUT
    staging.DEST = DEST
    staging.EXPECTED = 'df3c29b2e3152578e2f4de29eaa5c02743c8a823b5fae4904e39e96c6f94d18b'
    staging.main(required_tests=137, previous_usb_name='Insta360 Ace Pro S',
                 next_usb_name='Insta360 Ace Pro T', trial='T')
