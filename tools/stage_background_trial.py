"""Stage hash-pinned, validated Trial W on the identified camera running U."""
import stage_colour_trial as staging
from build_background_candidate import OUT, DEST

if __name__=='__main__':
    staging.OUT=OUT
    staging.DEST=DEST
    staging.EXPECTED='86b60ce8192e4789f3fb5d8a80a0cd0fa595c46564938d222d873263fec76fb1'
    staging.main(required_tests=156,previous_usb_name='Insta360 Ace Pro U',
                 next_usb_name='Insta360 Ace Pro W',trial='W')
