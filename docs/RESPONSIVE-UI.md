# Responsive UI source candidate (0.2.0)

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

This is host content rendering, not CM4 acceptance. Mac GTK is Quartz-only here;
there is no task-owned headless GTK backend. Production GTK header rendering,
Escape signals, fullscreen/compositor placement, actual touch and PTY behavior
need supported Pi OS ARM64 validation. All ten native UI sources pass syntax
checking, including the four Linux-media/remote UI files with the ARM64 compiler.
The cached cross sysroot lacks ARM64 GTK libraries and the environment refuses
Docker socket/SSH access. Therefore native 0.2.0 debs have not been rebuilt or
deployed by this source check. Existing package descriptors continue to identify
the previously built payloads; the build script generates new descriptors only
after a successful package build. Historical 0.1.0 CM4 screenshots are labelled
as references, not evidence that this candidate was installed.
