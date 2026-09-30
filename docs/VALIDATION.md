# CM4 validation

Target: official Raspberry Pi OS Trixie, AArch64, CM4. Builds ran in a task-owned user cache with at most two compilation jobs. No package was installed, no production app/service was stopped, and no physical display, camera, audio device or USB configuration was changed.

## Verified paths

- Calculator: original parser/editing tests; actual GTK pointer clicks and physical key events both produced `2+3=5`. See `calculator-touch.png` and `calculator-keyboard.png`.
- Calendar: Gregorian 1900–2199, DST/2038, 42-day grids, ICS, local CRUD, private atomic persistence, corruption, capacity, opt-in built-ins, source deletion and URL deduplication tests.
- Gomoku: four win directions, occupied cells, undo, AI win/block selection, persistence/corruption and complete-game tests.
- Processing: four actual QuickJS examples ×180 frames, timeout recovery, heap limit, clipping and raster colors. Peak test RSS approximately 5 MiB for the model runner; this is not the GTK app or whole-system memory requirement.
- StreamPlayer: fresh XDG tree, actual loopback HTTP authentication fixture, `0600` configuration publication, reload and password exclusion. The fixture uses synthetic credentials; no media-server account was accessed.
- Mail: 13 synthetic protocol/UI tests covering bounded DNS/connect/TLS/SMTP/POP transactions, cancellation, malformed/oversize input, verified TLS and retry. Actual GTK Escape closes a stalled loopback socket while the UI remains responsive; see [network execution details](mail-network.md). No real account or email delivery was accessed.
- Escape routing: production GTK physical-key and toolbar signals exercise Processing run/editor return/save and Airtune/StreamPlayer busy cancellation, late-success suppression, drain-before-retry and cancellation of an actual stalled loopback HTTP request.
- Bilibili decoder: production desktop MPlayer/YUV/GTK path decoded 45 frames from a locally generated H.264 MP4. Audio was disabled. No external video/account was used for this check.
- Piano: actual PCM synthesis→GStreamer conversion→48 kHz stereo silent sink. GUI keyboard is rendered from the production code. Audible output still needs a physical check.
- Camera: all 96 crop/look/paper combinations and synthetic preview→capture→JPEG→album; low-storage/cancel/permissions/atomic-save checks. Camera screenshots explicitly show the synthetic test pattern.
- HIDPilot: complete printable ASCII mapping, HID report layouts, rollover, endpoint validation, bounded queue and release behavior via a pipe. No physical host reports were sent.
- DOS/PS1 frontend: local import/command construction and persistence; PS1 BIOS partial ENOSPC failure cleans up, retry succeeds, existing firmware is preserved, and files publish privately. No ROM/BIOS or game-compatibility claim is included.
- Complete-deb inspection uses the existing Store validator against each payload and checks release SHA-256/control metadata. `apt-get -s install` simulates dependency resolution only.

The all-app UI runner extracts complete debs into a private prefix, gives every app separate HOME/XDG state, and renders on a task-owned Xvfb. It waits for actual Python first-frame callbacks, requires nonempty 800×600 pixel captures, and waits for clean application exits. Every X server/app it starts is closed in `finally`. This startup check does not certify authenticated media/mail/Sunshine services, physical touch, speakers, cameras, USB-host reception or user game performance.

## Reproduce

```sh
sh upstream/calculator/tests/run.sh
sh upstream/calendar/tests/run.sh
sh upstream/gomoku/tests/run.sh
./build/c1max-sketch-test ./upstream/processing
python3 tests/test_first_run.py
python3 tests/test_game_library.py
TYPIX_MAIL_XVFB=/path/to/task-owned/Xvfb python3 tests/test_mail_network.py
TYPIX_XVFB=/path/to/task-owned/Xvfb python3 tests/test_escape.py
python3 extras/piano.py --smoke-test
python3 extras/piano.py --audio-smoke-test
python3 extras/camera.py --smoke-test
python3 extras/hidpilot.py --smoke-test
TYPIX_XVFB=/path/to/task-owned/Xvfb python3 tools/smoke_suite.py
python3 tools/check_packages.py --store-validator /path/to/store_publication.py --simulate-dependencies
```

`tools/test_media.py` and `tools/input_check.py` provide the isolated decoder/input checks. Their paths are CM4 QA defaults and can be adapted to another isolated build machine; they never install their runtime dependencies. Source provenance and hashes are recorded in `SOURCE-PROVENANCE.json`. Final package hashes and screenshots are in each `packages/<app>/app.json`; task build logs remain under the excluded `build/` tree.
