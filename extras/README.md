# Native Linux Piano, Instant Camera and HID Keyboard & Mouse

These are independent GTK3 applications for the Linux desktop. They run as the
logged-in user in ordinary compositor-managed windows and fit an 800×600 display.
They do not open a framebuffer, stop a desktop, retain root privileges, change
USB configuration, write device controls, contact a network service, or collect
device identifiers. Each module exports `main(argv=None)` and can be run directly.

## Packaging interface

| Application | Entry | Required files | Debian dependencies |
| --- | --- | --- | --- |
| Piano | `python3 piano.py` | `piano.py` | `python3`, `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`, `gir1.2-gstreamer-1.0`, `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good` |
| Camera | `python3 camera.py` | `camera.py` and sibling `assets/` recursively | Same as Piano, plus `python3-pil`, `gir1.2-gst-plugins-base-1.0` |
| HID | `python3 hidpilot.py` | `hidpilot.py` | `python3`, `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0` |

Piano and the camera shutter use the system-selected GStreamer audio sink. A
working sink such as the distribution's PulseAudio/PipeWire compatibility sink
or `gstreamer1.0-alsa` is needed for sound. No mixer, amplifier or system volume
is changed. Python 3.9+ and Pillow 9.1+ are supported; the CM4 validation machine
had Python 3.13, GTK 3, GStreamer 1.26.2 and Pillow 11.1.0.

There is no dependency on this checkout, an upstream checkout, SSH, or a fixed
home directory. Assets are resolved relative to `camera.py`. `verify_ui.py` and
`qa/` are development evidence and need not be installed.

## Piano

- 24 keys, C4 through B5; independent oscillators, 4 ms attack, 180 ms release.
- Real signed 16-bit PCM synthesis through GStreamer `appsrc`, normal audio
  conversion/resampling and the system audio sink. No generated music file or
  external synthesizer service is needed.
- Touch, pointer drag and physical keys share note ownership, so releasing a
  pointer does not release a note still held on the keyboard. Keyboard polyphony
  works independently of the touchscreen's physical multitouch capability.
- Lower octave: `Z S X D C V G B H N J M`; upper octave:
  `Q 2 W 3 E R 5 T 6 Y 7 U`. Key labels appear on the piano.
- Volume, Release all, Retry audio; focus loss releases notes. Esc exits.
- Audio begins on the first note. Device/sink failure is visible and retryable.

Piano keeps no persistent data. It does not reproduce the original C1 Max's
Ingenic-specific mixer setup, rotated framebuffer or raw input calibration.

## Instant Camera

- Enumerates accessible V4L2 capture nodes using `VIDIOC_QUERYCAP`. The user
  selects a device and starts it explicitly. GStreamer `v4l2src`/`decodebin`
  accepts driver-exposed raw and decodable compressed camera formats.
- Real live RGB preview, bounded to at most 4096×4096 source pixels; RGB
  conversion respects the negotiated row stride. UI preview is refreshed at up
  to 10 Hz; only the latest frame is retained.
- Center crops: 4:3, 3:4, 1:1 and 16:9. Looks: Original, Mono, Sepia, Warm, Cool,
  Faded with vignette. Papers: None, White, Cream, Film. Manual 0/90/180/270°
  rotation handles camera mounting without a board-model assumption.
- Preview and JPEG use the same crop/filter/frame compositor. The original
  RGBA paper artwork is mapped in nine sections; the aperture remains clear.
  Textures are cached at 512×512 for bounded live-preview work. The saved image
  has at most a 1600-pixel photograph edge before paper margins are added.
- Shutter freezes a frame and saves JPEG quality 92 on a worker thread. Cancel
  leaves no partial photograph; success flashes the preview and plays the
  original short mechanical shutter sound at the existing system volume.
- Photos are private `0600` files, published under unique names only after JPEG
  writing and syncing completes. A 32 MiB free-space reserve is checked.
- Album browsing stops camera capture. It supports JPEG/EXIF orientation,
  bounded decode, previous/next, and confirmed deletion. Symlinks are excluded;
  deletion checks the selected file's identity and album membership.
- Camera errors, permission errors, missing devices and five seconds without
  frames produce a visible retryable error. No microphone or video recording.

Data is local in `${XDG_DATA_HOME:-$HOME/.local/share}/c1max-camera/`:
`settings.json` remembers ratio/look/paper/rotation; `photos/` holds JPEGs.
The album shows that directory when empty. There is no upstream data-directory
assumption and no automatic import or migration.

Controls: Space captures; `R`, `F`, `B` cycle ratio/filter/paper; `G` toggles the
album; arrows or `A`/`D` browse; Delete/Backspace/`X` asks to delete; Esc returns
from the album, cancels a capture, or closes the camera. GTK controls are also
keyboard and touch accessible.

This is a V4L2 application. CSI cameras available only through libcamera are not
claimed as supported unless a compatible V4L2 capture endpoint is exposed. It
does not configure sensor media graphs, autofocus, exposure or ISP registers.
The source camera's legacy sideways-file filename heuristic is not applied;
this port writes correctly oriented files and reads standard EXIF orientation.

## HID Keyboard & Mouse

- Opens **only existing, explicitly selected `/dev/hidgN` character nodes**,
  without symlink traversal, after the user confirms the expected report layout
  and presses Start. No node is opened during discovery or startup.
- Two layouts: separate 8-byte boot keyboard and 4-byte relative mouse; or the
  C1Max combined report layout (keyboard report ID 1, relative mouse ID 3).
  For a combined node, select the same node for keyboard and mouse. Either
  endpoint may be disabled. Arbitrary descriptors are not autodetected.
- Touchpad movement and tap-to-click, held left/right buttons, scroll, sticky
  Ctrl/Shift/Alt/Super, Esc/Tab/arrows/Enter buttons, and optional physical
  keyboard forwarding. Physical forwarding is off until explicitly enabled.
- US ASCII usage mapping, modifier state and six-key rollover. For other text,
  select an input method on the connected host. This is manual local input only.
- Esc releases all input and disables physical forwarding; F12 stops the
  connection. Focus loss releases input and disables physical forwarding.
- Bounded nonblocking report queue and a one-second stalled-host timeout.
  Stop/exit makes a bounded best effort to release host keys/buttons, then
  closes only this app's descriptors. A disconnected host may require reconnect.
- Missing nodes or insufficient permissions are shown in the window. No USB
  gadget, configfs, FunctionFS, module, udev, root or system-service mutation.

HID keeps no persistent data. USB gadget support and compatible report
descriptors are administrator/device prerequisites, not an app claim based on
CM4/CM5 model names. The original app's automatic USB reconfiguration is
deliberately outside this Linux application's authorization boundary.

## Validation

Run these without a display or physical devices:

```sh
python3 piano.py --smoke-test
python3 piano.py --audio-smoke-test
python3 camera.py --smoke-test
python3 hidpilot.py --smoke-test
```

The audio check runs the production PCM pipeline with a silent `fakesink` and
asserts conversion to 48 kHz stereo. It does not claim physical sound output.
Camera checks all 96 ratio/look/paper combinations, aperture pixels, ratio
geometry, JPEG decode, file permissions, atomic publication, low free space,
cancellation, changed-file rejection, symlink exclusion and deletion. HID checks
all printable ASCII characters, report layouts, rollover, endpoint restrictions,
queued press/release delivery and stop release using a pipe, without HID access.

For isolated UI verification, use a task-owned Xvfb binary:

```sh
python3 verify_ui.py --xvfb /path/to/Xvfb --output /tmp/c1max-extras-qa
```

The runner starts an isolated 800×600 display, checks the three actual GTK
windows and screenshots, and always stops its child apps and X server. Camera
uses a GStreamer test pattern, selects a crop/filter/paper, captures a real JPEG
in a temporary album and reads it back. Piano avoids the audio device; HID does
not open an endpoint. `--ui-smoke-test` is also available on each application.
Its optional `C1MAX_UI_SCREENSHOT` environment variable specifies a screenshot
path only during this synthetic UI test mode.

2026-10-01 acceptance on the Raspberry Pi CM4: all four noninteractive checks
passed; all three isolated UI checks passed at 800×600. Screenshots are in
`qa/`. A full 24-voice 0.5-second synthesis block took 0.293 seconds on that
machine. All task-owned Xvfb/app processes were waited for and exited. No live
desktop, package installation, service restart, USB configuration, real camera
stream or physical HID host was involved. Audible speakers, physical touch,
real camera image quality and host-received USB reports still need manual
hardware acceptance; synthetic results are not represented as those checks.

## Source and attribution

Behavior references are the tracked, read-only C1Max sources at commit
`b7930c572715688595bb3bba1fbdc7a08df9e88a` in
`https://github.com/zhuzhe1983/C1Max-Apps`: `piano`, `camera`,
`hidpilot`, and `shared/usb_keys.hpp`.
The Python/GTK integrations and tests are new Linux implementations; they do
not bundle tinyalsa, stb, LVGL, the original hardware backend or privileged
USB helper. Upstream contributor attribution belongs to C1Max-Apps contributors.

`assets/frames/{white,cream,film}.{png,window}`, `assets/frame-prompts.json`,
and `assets/shutter.wav` are copied unchanged from upstream Camera. Its README
identifies the paper artwork as original image_gen outputs and the shutter
sample as an original deterministic synthesis, without external audio samples.
Preserve these provenance files and the suite's upstream license/notices when
packaging; this directory does not replace upstream license metadata.
