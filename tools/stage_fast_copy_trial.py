"""Stage hash-pinned Trial R after regression and independent package checks."""
import stage_colour_trial as staging
from build_fast_copy_candidate import OUT, DEST


if __name__=='__main__':
    staging.OUT=OUT
    staging.DEST=DEST
    staging.EXPECTED='4e25037dba980f025e1bc3a244a3ae2ddaa0a5f567f262c9e0d33bb0adf239c6'
    staging.main(required_tests=114,previous_usb_name='Insta360 Ace Pro Q',
                 next_usb_name='Insta360 Ace Pro R',trial='R')
