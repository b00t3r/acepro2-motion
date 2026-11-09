"""Stage validated memory-only Trial X on the identified camera running W.

This is a prerequisite, not the requested higher-resolution feature itself.
The reusable stager checks card UUID, USB identity, space and readback before
safely ejecting. Installation is verified separately after a user-run update.
"""
import stage_colour_trial as staging
from build_highres_memory_candidate import OUT, DEST


if __name__ == '__main__':
    staging.OUT = OUT
    staging.DEST = DEST
    staging.EXPECTED = '519dfd45b163e53259acd6f6c0dc7c061b0c2d1f0d53d80ff47b43c1b4e84846'
    staging.main(required_tests=189, previous_usb_name='Insta360 Ace Pro W',
                 next_usb_name='Insta360 Ace Pro X', trial='X (memory-only prerequisite)')
