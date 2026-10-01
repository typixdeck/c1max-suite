# Public C1Max inventory and port architecture

Inventory source: public `catalog.json`, 18 entries (private/local application configuration excluded).

| Public app | TypixDeck delivery | Retained functions / limitations |
|---|---|---|
| launcher | Existing `typix-launcher` | Desktop discovery, keyboard navigation, new lifecycle policy owned by Launcher workstream |
| crosspoint | Existing `typix-reader` | Local books + Calibre OPDS; broader PDF rendering already available; no overwrite |
| nes | Existing `typix-gamer` + `libretro-nestopia` | NES library/import and RetroArch; user ROM required; no new duplicate frontend |
| calculator | `typix-calculator` | Original parser, editing/history logic and LVGL UI |
| calendar | `typix-calendar` | Month view, local schedules, ICS subscriptions/import/export |
| gomoku | `typix-gomoku` | Original human/AI/two player/undo/persistence |
| terminal | `typix-terminal` | Original PTY/libvterm plus distro bash, less, nano, SSH tools |
| processing | `typix-processing` | Original sandbox-bounded QuickJS 2D subset/editor and licensed example adaptations |
| airtune | `typix-airtune` | Original radio directory, search, favorites/custom stations; desktop audio |
| streamplayer | `typix-streamplayer` | Original Emby/Jellyfin auth/library/server-transcoded media/subtitles |
| bilibili | `typix-bilibili` | Original public feed/search/BV/QR auth/history/direct MP4; service may change; no DASH/live |
| mail | `typix-mail` | Original POP3+SMTP TLS client; no IMAP/OAuth/attachments; account needed for real delivery |
| moonpilot | `typix-moonpilot` | Original GameStream pairing, H264 desktop/manual input/AI/voice; host/service setup required; host audio retained |
| piano | `typix-piano` | GTK/GStreamer audible synthesis, keyboard/touch |
| camera | `typix-camera` | GTK/GStreamer V4L2 preview, capture/filter/crop/frame/album; discover actual compatible camera |
| hidpilot | `typix-hidpilot` | Manual keyboard/mouse only on preconfigured accessible HID nodes; never configures USB or root |
| dosbox | `typix-dosbox` | Native game-directory library + distribution DOSBox interpreter, game saves preserved |
| pcsx4all | `typix-ps1` | Native disc library/BIOS import + distribution Mednafen PS1; user disc/BIOS, performance depends on runtime |

The 10 C++ applications reuse their full audited tracked application source. Their common display/input implementation is replaced with GTK3/Cairo compositor windows: no exclusive framebuffer, evdev grabs, C1Max system properties, or display ownership tricks. The 0.2.0 candidate reflows actual widgets into the available window content instead of letterboxing the original 800×340 canvas. Fonts retain their proportions; images use aspect-preserving containment. A compact native Back/menu header replaces the common bottom navigation/software-keyboard panel. The menu retains optional native GTK input/paste; app-specific touch actions and physical keyboard bindings remain. Terminal reports actual grid and viewport sizes to its PTY. The Piano/HID/library GTK views use natural expandable content, and library actions sit next to the library heading. Camera is unchanged at 0.1.0. F10 closes, F11 toggles fullscreen, Alt+Tab remains owned by the desktop compositor. The original applications use Escape to go back/cancel and F2 for their symbol prefix. While Airtune or StreamPlayer is busy, Escape first cancels the current request; another Escape navigates back after cancellation finishes. A cancelled worker is drained before new work and its late result is discarded. Calculator uses Escape to clear; Terminal receives a normal ESC byte. All 15 applications start fullscreen and expose a unique matching `typix-<app>` compositor identity; `TYPIX_WINDOWED=1` is available for isolated QA.

Each new deb owns its complete private installation prefix, application binary/script, assets/fonts/licenses and desktop file. No common file conflicts or private snapshots. XDG user data remains outside packages; packages have no maintainer scripts or root UI. Native binary build compatibility is detected from the build OS, never advertised as Bookworm-compatible when built on Trixie.

Runtime network features are user-driven and retain timeout/cancel/error paths. No account or server is preconfigured. Camera/HID absence is a capability state, not a successful hardware test. No production apps were stopped, no devices flashed, no package installed while building/testing this suite.

The 0.2.0 source has host framebuffer evidence at 800×600, 1024×768 and 1280×800, described in [RESPONSIVE-UI.md](RESPONSIVE-UI.md). All ten native 0.2.0 ARM64 debs were rebuilt and their extracted binaries passed isolated Debian Trixie GTK/Xvfb startup, rendering and exit checks; production GTK Escape/header Back regression checks also passed. These screenshots are labelled separately from historical CM4 references. Physical CM4 compositor, touch, audio and external-service acceptance remain pending.
