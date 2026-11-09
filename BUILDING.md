# Building and testing

The working build targets the Ace Pro 2 and the exact **2.0.51** firmware used in this project. It has been rebuilt on macOS; other platforms and compiler versions have not been verified.

You'll need Python 3, `clang` with AArch64 support, and these two original firmware files in the project root:

- `Insta360AcePro2FW.bin` — the 2.0.51 update.
- `Insta360AcePro2FW.bin.old.bin` — the earlier 2.0.50 update used for package checks.

The firmware files are not included. The build checks that both files match the versions used here before making any changes. Obtain them yourself and check the applicable terms before distributing firmware.

Create a virtual environment and install the Python requirements:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Build the tested T3 package:

```sh
.venv/bin/python tools/build_working_firmware.py
```

This runs the existing build steps, checks the final output against the tested build, and writes it under `builds/offline-gallery-motion/`. It also creates or overwrites generated files in `builds/` and `analysis/`. It does not install anything on the camera.

To run a set of ARM emulation tests after building:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_livephoto_trial_five.py' -v
```

These tests simulate parts of the firmware with mocked camera services; they are not a full camera emulator. Some other tests still require local capture files or additional experimental builds that are not included in the repository.
