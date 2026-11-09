# Live Photos on the Insta360 Ace Pro 2

I bought an action camera for one very specific reason: it can take Live Photos! There was just one problem. The camera saves a photo, a video and another file for its own gallery. I wanted a **Google Motion Photo**: one picture with the video inside it.

I have a camera. I have a code assistant. Let's go!

This project modifies the Ace Pro 2 firmware so the camera creates that Motion Photo itself. The bigger goal? Take those little videos and turn them into a **movie of the day**. A fun way to look back at the moments between the pictures.

## What works

- [x] Create a Google Motion Photo on the camera, using the still photo and the existing 720p preview video.
- [x] Use **2× zoom** for Live Photos, with the zoom reflected in both the photo and video.
- [x] View the combined picture in the camera gallery and play its motion in Google Photos.
- [x] Move Motion Photo processing to the background to help the camera get ready for the next shot sooner.
- [x] Reduce the size of the separate main video by lowering its bitrate in the tested modes.

There's still a catch: **the camera also keeps the original JPG, LRV and MP4 files**. Automatic cleanup isn't finished yet.

## What's next?

- [ ] Safely keep just the Motion Photo, without all the extra files.
- [ ] Explore higher-resolution Live Photo stills and 1080p embedded video.
- [ ] Create a movie of the day from the embedded clips.
- [ ] Explore custom button behaviour and sleep settings.
- [ ] Make the build process easier for others to follow and test more camera settings.
- [ ] Profit!

## Try it

The working experimental build is **Trial T3**, based on Ace Pro 2 firmware **2.0.51**. The firmware binary isn't stored in the repository. See [building and testing](BUILDING.md) if you'd like to build it from the original firmware files.

With the build installed, take a Live Photo and look for the `.MP.jpg` file in `DCIM/Camera01`. Upload it to Google Photos and give it time to process. Keep the original files until you've checked the result and made a backup.

For those who want to dig in, start with the [firmware findings](analysis/REPORT.md), [Motion Photo builder](tools/motion_photo_payload.c), and [background worker](tools/motion_worker_port.c). There's also a [tool for joining Motion Photo clips](tools/motion_photos_to_movie.py) on a computer.

## Build and test

You'll need **Python 3**, **clang with AArch64 support**, and the original Ace Pro 2 firmware files in the project folder:

- `Insta360AcePro2FW.bin` — version 2.0.51
- `Insta360AcePro2FW.bin.old.bin` — version 2.0.50

Then run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/build_working_firmware.py
.venv/bin/python -m unittest discover -s tests -p 'test_livephoto_trial_five.py' -v
```

The build has been verified on macOS. The tests simulate parts of the firmware, not the whole camera. See [building and testing](BUILDING.md) for details.

## A few important notes

This is an independent experiment, created with the help of a **code assistant**. It has been tested on one camera, not every setting or situation. Modified firmware can cause problems, including lost files or a camera that won't boot. Back up your photos and keep the original firmware before experimenting; recovery is not guaranteed.

This project isn't affiliated with Insta360. We did not crack a firmware-signing key, and the camera's full signing policy is still unknown.
