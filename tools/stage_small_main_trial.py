"""Stage the hash-pinned Trial P after its full offline validation."""
import stage_colour_trial as staging
from build_small_main_candidate import OUT, DEST


if __name__ == '__main__':
    staging.OUT = OUT
    staging.DEST = DEST
    staging.EXPECTED = 'af1560cb0ff0cac32dedb9217b76edf2060ad14ad93498611d33ee216c9a54b6'
    staging.main(required_tests=102, previous_usb_name='Insta360 Ace Pro N',
                 next_usb_name='Insta360 Ace Pro P', trial='P')
