# Responsive UI (0.2.0)

The maintained native application ports now use available TypixDeck desktop
content, including 800×600, 1024×768 and wider windows. The actual application
widgets reflow; the old C1Max framebuffer is not presented as a device simulator.
GTK owns the fullscreen window and input, while the original application models
and LVGL widgets remain the implementation.

The common persistent Esc/Tab/arrow/Enter row, software keyboard and input field
are replaced with a compact dark native Back/menu header. The menu contains
keyboard help, Close and optional native text/paste input. This preserves the
existing native IME entry path; each app still enforces its own accepted characters
and limits. Physical keyboard operation remains available. Mail now has real
Receive/Compose/Account actions and selectable rows/fields in its own content.
Changing a touched mail field commits the previous field instead of dropping it.

Widget coordinates and panel sizes follow the content viewport. Fonts keep their
aspect ratio. The production GTK drawing area maintains an 800-pixel logical width
and derives its height from the actual allocation, then paints uniformly into
the window. Image previews use containment, and Gomoku/Processing/MoonPilot map
touch coordinates into the displayed source image, rejecting letterbox margins.
Terminal adjusts its actual libvterm/PTY rows and columns and reports viewport
pixel dimensions. Piano retains real audio controls; HID retains real endpoint
controls; DOS/PS1 library actions sit with the heading. Camera source and its
existing 0.1.0 package are held unchanged because no TypixDeck camera is present.

## Current local evidence

`tools/test_responsive.py` compiles the **production Calculator, Calendar and Mail
source pages** with real LVGL/Cairo and an explicit offline transport fixture.
It does not draw substitute screenshots. It performs no network requests,
authentication, persistence, device I/O, package installation or system changes.

Passing checks cover live object repositioning/resizing, unchanged font metrics,
centered labels, percentage/content dimensions, cleaned/deleted widgets, portrait
layout basis, aspect-preserving image hit tests, all top-level widget bounds, real
calculator touch and physical calculation, and mail touch field transitions.
The rendered content viewports are 800×600, 1024×768 and 1280×800. Mail examples are
synthetic offline inbox contents. Calendar uses a fixed October 2026 date.

| Content preview | 800×600 | 1024×768 | 1280×800 |
|---|---|---|---|
| Calculator | [render](screenshots/calculator-responsive-800x600.png) | [render](screenshots/calculator-responsive-1024x768.png) | [render](screenshots/calculator-responsive-1280x800.png) |
| Calendar | [render](screenshots/calendar-responsive-800x600.png) | [render](screenshots/calendar-responsive-1024x768.png) | [render](screenshots/calendar-responsive-1280x800.png) |
| Mail | [render](screenshots/mail-responsive-800x600.png) | [render](screenshots/mail-responsive-1024x768.png) | [render](screenshots/mail-responsive-1280x800.png) |

Run from the repository root, with CMake, a C++17 compiler and Cairo development
headers installed:

```sh
python3 tools/test_responsive.py
# Optional reuse of a matching locally built LVGL static library:
python3 tools/test_responsive.py --lvgl-library /path/to/liblvgl.a
```

This host content rendering is separate from the ARM64 GTK checks below. Actual
CM4 compositor placement, physical touch, audio and externally configured
services still require supported Pi OS ARM64 acceptance. Historical 0.1.0 CM4
screenshots are retained as references, not evidence of a 0.2.0 device install.

## ARM64 package validation

On 2026-10-01, all ten native applications were rebuilt from the maintained
source using `tools/Dockerfile.trixie-arm64` and explicit `--platform linux/arm64`.
The build image used Debian Trixie ARM64 and GTK 3; it was isolated from the Pi.
Packages declare `raspios-trixie`, never Bookworm compatibility. Packaging
checked the ELF64 little-endian ARM64 machine type, derived dynamic dependencies
with `dpkg-shlibdeps`, and included the actual fonts, resources and licenses.
Camera source, descriptor, screenshot and 0.1.0 deb remain unchanged.

Ten extracted 0.2.0 debs started and rendered in a task-owned 800×600 Xvfb.
Each process exited with code 0 and Xvfb was closed. Their `*-0.2.0-arm64.png`
screenshots contain the production GTK header and application UI. All state was
temporary, and the test container had no external network access.

| Actual ARM64 GTK screenshot | Actual ARM64 GTK screenshot |
|---|---|
| [Calculator](screenshots/calculator-0.2.0-arm64.png) | [Calendar](screenshots/calendar-0.2.0-arm64.png) |
| [Gomoku](screenshots/gomoku-0.2.0-arm64.png) | [Terminal](screenshots/terminal-0.2.0-arm64.png) |
| [Processing](screenshots/processing-0.2.0-arm64.png) | [Airtune](screenshots/airtune-0.2.0-arm64.png) |
| [StreamPlayer](screenshots/streamplayer-0.2.0-arm64.png) | [Bilibili](screenshots/bilibili-0.2.0-arm64.png) |
| [Mail](screenshots/mail-0.2.0-arm64.png) | [MoonPilot](screenshots/moonpilot-0.2.0-arm64.png) |

The same ARM64 build passed production GTK Escape and header Back signals for
Processing, Airtune and StreamPlayer, including request cancellation, late-result
rejection and retry recovery through a stalled loopback HTTP fixture. QuickJS
demo execution, timeout recovery, heap limits and raster checks passed. The
first-run StreamPlayer fixture checked private state creation, account reload
and password exclusion. These fixtures use synthetic credentials and no real
account or server.

Reproduce after the native build:

```sh
docker run --rm --platform linux/arm64 --network none -e TYPIX_XVFB=/usr/bin/Xvfb \
  -v "$PWD:/work" typix-c1max-builder:trixie-arm64 sh -c \
  'build/c1max-sketch-test upstream/processing && python3 tests/test_escape.py && python3 tests/test_first_run.py && python3 tools/smoke_suite.py --apps calculator calendar gomoku terminal processing airtune streamplayer bilibili mail moonpilot --suffix=-0.2.0-arm64'
```

Re-run `tools/build_debs.py` after capturing screenshots to include the accurate
per-package screenshot metadata. The final packages keep the same native ELF
payloads that were exercised by the screenshot run. No package was installed on
the CM4 during this build or isolated validation.

The final 15-package complete-payload/hash/control validation and Trixie ARM64
`apt-get -s` dependency simulation passed. Build source, tool versions, image
digest, package hashes and exercised ELF hashes are recorded in
[BUILD-PROVENANCE-0.2.0.json](BUILD-PROVENANCE-0.2.0.json).
