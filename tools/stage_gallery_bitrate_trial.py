"""Stage hash-pinned Trial Q after full regression and package validation."""
import stage_colour_trial as staging
from build_gallery_bitrate_candidate import OUT, DEST


if __name__ == '__main__':
    staging.OUT = OUT
    staging.DEST = DEST
    staging.EXPECTED = '814e4a727f72def6d19f43e6cb4a0614449d1d4c61321712db21a0d9eea1b5e3'
    staging.main(required_tests=108, previous_usb_name='Insta360 Ace Pro P',
                 next_usb_name='Insta360 Ace Pro Q', trial='Q')
