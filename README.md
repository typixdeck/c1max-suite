# TypixDeck C1Max native suite

Ports of the complete 18-entry public C1Max catalog for official Raspberry Pi OS ARM64. The existing Typix Launcher, Reader and Gamer fulfill Launcher, CrossPoint and NES without replacing their files or data. This suite provides the other 15 individually installable complete debs. See [inventory and limits](docs/PORT-STATUS.md).

Ten applications preserve their original C++/LVGL application logic in compositor-managed GTK3 windows. Piano, Camera and HIDPilot use native GTK3 implementations. DOS and PS1 have real local-library/session frontends backed by the distribution DOSBox and Mednafen packages. No browser runtime, device snapshots, ROM, BIOS or account configuration is included.

## CM4 interface previews

![Calculator: actual keyboard calculation](docs/screenshots/calculator-keyboard.png)

![Piano: isolated native keyboard view](docs/screenshots/piano.png)

![Calendar: native month and agenda view](docs/screenshots/calendar.png)

## Build

On the target distribution, provide build dependencies `build-essential cmake pkg-config libgtk-3-dev dpkg-dev python3` through the normal audited system administration path. Building does not install packages.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
python3 tools/build_debs.py --repository OWNER/REPOSITORY
```

The repository argument is an explicit source-publication input. The script creates `packages/<app>/app.json` and its complete `dist/*.deb`. It does not create that repository, sign, upload, install or publish. Native dependencies are derived using `dpkg-shlibdeps`; distro compatibility matches the build host. A Trixie binary is not advertised as Bookworm-compatible.

Native applications install real ARM64 ELF commands at `/usr/bin/typix-<app>` with matching desktop files, resources and licenses. Python apps install their full implementation. Each package has its own resource prefix and declares system runtimes in Depends. There are no package maintainer scripts and no shared files that conflict between packages.

## Desktop controls and data

F10 exits native LVGL apps, F11 toggles fullscreen, Escape goes back/cancels, F2 is the original symbol-prefix key. Alt+Tab stays with the desktop. The bottom row provides touch arrows, Enter, Esc and a Keys panel. Text is also accepted through the native GTK input field. Original source layouts use an 800×340 logical canvas inside the 800×600 desktop window, preserving aspect ratio.

Application data stays under `$XDG_DATA_HOME/typix-c1max/<app>` (default `~/.local/share/typix-c1max`) for C++ ports. DOS/PS1 use their own `typix-<app>` XDG directory. Camera uses `$XDG_DATA_HOME/c1max-camera`; Piano/HID keep no persistent data. No existing Reader, Gamer, Launcher or Copilot data is touched. Package upgrade/remove does not remove user data. No privileged GUI or system/USB/MUX/display configuration is performed.

HID requires already-configured writable keyboard/mouse gadget nodes and correct report layouts; camera requires an actually compatible V4L2 device; PS1 requires legal game/BIOS files. Media, mail, Sunshine and AI features require user-configured services. See per-app source documentation for inherited protocol and format limits. Real physical hardware/service acceptance must be reported separately from isolated startup/logic checks.

## Source and licenses

`upstream/` was imported only from the read-only public tracked C1Max application set. The dependency commits/checksums are preserved in `upstream/dependencies.json` and `upstream/archives.json`. No ignored local app, configuration, private server, data, cache or compiled binary was imported. `port/` replaces hardware-specific display/input and desktop integrations. Original third-party GPL, MIT, Apache, zlib and OFL notices accompany the source and every generated deb. GPL-linked Bilibili/MoonPilot binaries require this corresponding source and build recipes to be made available with publication. No public-repository publication is performed by these tools.

## Applications

| Application | Source / package descriptor | Verified UI |
| --- | --- | --- |
| 计算器 / Calculator | [packages/calculator](packages/calculator/app.json) | [CM4 screenshot](docs/screenshots/calculator.png) |
| 日历 / Calendar | [packages/calendar](packages/calendar/app.json) | [CM4 screenshot](docs/screenshots/calendar.png) |
| 五子棋 / Gomoku | [packages/gomoku](packages/gomoku/app.json) | [CM4 screenshot](docs/screenshots/gomoku.png) |
| 终端 / Terminal | [packages/terminal](packages/terminal/app.json) | [CM4 screenshot](docs/screenshots/terminal.png) |
| 创意绘图 / Processing 2D | [packages/processing](packages/processing/app.json) | [CM4 screenshot](docs/screenshots/processing.png) |
| 网络电台 / Airtune | [packages/airtune](packages/airtune/app.json) | [CM4 screenshot](docs/screenshots/airtune.png) |
| 流媒体 / StreamPlayer | [packages/streamplayer](packages/streamplayer/app.json) | [CM4 screenshot](docs/screenshots/streamplayer.png) |
| 哔哩哔哩 / Bilibili | [packages/bilibili](packages/bilibili/app.json) | [CM4 screenshot](docs/screenshots/bilibili.png) |
| 邮件 / Mail | [packages/mail](packages/mail/app.json) | [CM4 screenshot](docs/screenshots/mail.png) |
| 远程桌面 AI / MoonPilot | [packages/moonpilot](packages/moonpilot/app.json) | [CM4 screenshot](docs/screenshots/moonpilot.png) |
| 钢琴 / Piano | [packages/piano](packages/piano/app.json) | [CM4 screenshot](docs/screenshots/piano.png) |
| 拍立得 / Camera | [packages/camera](packages/camera/app.json) | [CM4 screenshot](docs/screenshots/camera.png) |
| USB 键鼠 / HIDPilot | [packages/hidpilot](packages/hidpilot/app.json) | [CM4 screenshot](docs/screenshots/hidpilot.png) |
| DOS 游戏库 / DOSBox | [packages/dosbox](packages/dosbox/app.json) | [CM4 screenshot](docs/screenshots/dosbox.png) |
| PS1 游戏库 / PS1 Library | [packages/ps1](packages/ps1/app.json) | [CM4 screenshot](docs/screenshots/ps1.png) |

Existing Launcher/Reader/Gamer remain separately maintained. The machine-readable full 18-app mapping is [catalog-mapping.json](catalog-mapping.json). Source repository: https://github.com/typixdeck/c1max-suite. Publication tools build reviewable candidates and never create repositories, upload or publish automatically.
