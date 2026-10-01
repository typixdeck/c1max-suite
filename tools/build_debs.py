#!/usr/bin/env python3
"""Build complete per-app Debian payloads. No install, upload or signing.

Run natively on official Pi OS ARM64 after CMake. Pure Python packages may
also be assembled with an explicit target OS; this does not validate runtime.
Repository is an explicit
publication input so development cannot invent a hosted source repository.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.0-1'
APPS = {
    'calculator': ('计算器', 'Calculator', 'Utility', '四则、括号、乘方、历史与实体键盘计算', ''),
    'calendar': ('日历', 'Calendar', 'Office', '月历、本地日程、ICS 导入导出与订阅', 'wget, ca-certificates'),
    'gomoku': ('五子棋', 'Gomoku', 'Game', '人机与双人五子棋、悔棋和自动续局', ''),
    'terminal': ('终端', 'Terminal', 'System', '完整 PTY、ANSI、UTF-8 终端和 Linux 命令工具', 'bash, less, nano, openssh-client, ncurses-term'),
    'processing': ('创意绘图', 'Processing 2D', 'Development', 'QuickJS 驱动的 Processing 风格 2D 子集与草图编辑器', ''),
    'airtune': ('网络电台', 'Airtune', 'AudioVideo', '电台目录、搜索、收藏、自定义电台与本地列表', 'mplayer, wget, ca-certificates, wireplumber'),
    'streamplayer': ('流媒体', 'StreamPlayer', 'AudioVideo', 'Emby/Jellyfin 登录、媒体库、服务端转码视频及字幕', 'mplayer, wget, ca-certificates, wireplumber'),
    'bilibili': ('哔哩哔哩', 'Bilibili', 'AudioVideo', '热门、搜索、BV、分 P、扫码登录与直连 MP4', 'mplayer, wget, ca-certificates, wireplumber'),
    'mail': ('邮件', 'Mail', 'Network', 'POP3 收件与 SMTP TLS 纯文本邮件客户端', 'ca-certificates'),
    'moonpilot': ('远程桌面 AI', 'MoonPilot', 'Network', 'Sunshine 配对、远程桌面、手动输入与可配置 AI 和语音', 'mplayer, wget, ca-certificates, alsa-utils'),
    'piano': ('钢琴', 'Piano', 'AudioVideo', '键盘和触控复音钢琴与正常桌面音频输出', 'gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-alsa | gstreamer1.0-pulseaudio'),
    'camera': ('拍立得', 'Camera', 'Graphics', 'V4L2 取景、画幅滤镜、相纸边框与本地相册', 'gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-alsa | gstreamer1.0-pulseaudio, python3-pil'),
    'hidpilot': ('USB 键鼠', 'HIDPilot', 'Utility', '在已配置且有权限的 USB HID 节点上发送键鼠输入', ''),
    'dosbox': ('DOS 游戏库', 'DOSBox', 'Game', '本地 DOS 游戏目录、完整 DOSBox 运行与会话管理', 'dosbox'),
    'ps1': ('PS1 游戏库', 'PS1 Library', 'Game', 'PS1 光盘游戏库、BIOS 导入与 Mednafen 即时存档运行', 'mednafen'),
}
NATIVE = set(APPS) - {'piano', 'camera', 'hidpilot', 'dosbox', 'ps1'}
DEFAULT_APPS = [name for name in APPS if name != 'camera']


def screenshot_metadata(name, version):
    native = f'docs/screenshots/{name}-0.2.0-arm64.png'
    if name in NATIVE and version == '0.2.0-1' and (ROOT / native).is_file():
        return [{'path': native, 'caption': '0.2.0 ARM64 deb 实际 GTK 界面，800×600，隔离 Trixie/Xvfb；未验证 CM4 实体触摸、音频及外部服务'}]
    responsive = f'docs/screenshots/{name}-responsive-800x600.png'
    if name != 'camera' and (ROOT / responsive).is_file():
        return [{'path': responsive, 'caption': '本机源码 LVGL 内容渲染，800×600；未验证 CM4 GTK 窗口与实体触摸'}]
    caption = ('CM4 独立 800×600 合成相机测试画面' if name == 'camera' else
               '0.1.0 CM4 隔离显示中的界面参考；未验证本次候选版本')
    return [{'path': 'docs/screenshots/' + name + '.png', 'caption': caption}]


def copy(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
    else:
        shutil.copy2(src, dest)


def write(path, value, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(mode)


def native_depends(binary, temporary):
    debian = temporary / 'debian'
    debian.mkdir()
    write(debian / 'control', 'Source: typix-c1max\nSection: utils\nPriority: optional\nMaintainer: TypixDeck <dev@typixnode.com>\nStandards-Version: 4.6.2\n\nPackage: typix-c1max\nArchitecture: arm64\nDescription: Build dependency inspection\n')
    result = subprocess.check_output(['dpkg-shlibdeps', '-O', '-e' + str(binary)], cwd=temporary, text=True)
    return next(line.split('=', 1)[1] for line in result.splitlines() if line.startswith('shlibs:Depends='))


def build(name, args, codename):
    zh, english, category, summary, extras = APPS[name]
    package = 'typix-' + name
    root = ROOT / 'packages' / name
    dist = root / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    filename = f'{package}_{args.version}_{"arm64" if name in NATIVE else "all"}.deb'
    with tempfile.TemporaryDirectory(prefix=package + '-', dir=ROOT / 'build') as temp:
        stage = Path(temp) / 'stage'
        payload = stage / 'usr/share' / package
        executable = '/usr/bin/' + package
        required = [executable]
        if name in NATIVE:
            binary = ROOT / 'build' / ('c1max-' + name)
            blob = binary.read_bytes()[:20]
            if not (blob[:6] == b'\x7fELF\x02\x01' and int.from_bytes(blob[18:20], 'little') == 183):
                raise ValueError(f'{binary}: expected real ARM64 ELF')
            copy(binary, stage / executable.lstrip('/'))
            subprocess.run(['strip', '--strip-unneeded', str(stage / executable.lstrip('/'))], check=True)
            runtime = {'kind': 'native', 'path': executable}
            dependency_root = Path(temp) / 'dependencies'
            dependency_root.mkdir()
            depends = native_depends(binary, dependency_root)
            copy(ROOT / 'upstream/shared/fonts/NotoSansSC-Regular.ttf', payload / 'shared/NotoSansSC-Regular.ttf')
            required.append(str((payload / 'shared/NotoSansSC-Regular.ttf').relative_to(stage)).join(['/', '']))
            if name in {'terminal', 'processing'}:
                copy(ROOT / 'upstream/terminal/assets', payload / 'terminal/assets')
            if name == 'processing':
                copy(ROOT / 'upstream/processing/api.js', payload / 'processing/api.js')
                copy(ROOT / 'upstream/processing/examples', payload / 'processing/examples')
                required.extend(['/usr/share/' + package + '/processing/api.js', '/usr/share/' + package + '/processing/examples/tree.js'])
        else:
            source = ROOT / ('port/game_library.py' if name in {'ps1', 'dosbox'} else f'extras/{name}.py')
            target = payload / source.name
            copy(source, target)
            runtime = {'kind': 'python-script', 'path': '/' + str(target.relative_to(stage))}
            required.append(runtime['path'])
            write(stage / executable.lstrip('/'), '#!/bin/sh\nset -eu\nexec /usr/bin/python3 ' + runtime['path'] + ' "$@"\n', 0o755)
            depends = 'python3 (>= 3.11), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0'
            if name == 'camera':
                copy(ROOT / 'extras/assets', payload / 'assets')
        if extras:
            depends += ', ' + extras
        doc = stage / 'usr/share/doc' / package
        copy(ROOT / 'README.md', doc / 'README.md')
        copy(ROOT / 'docs/PORT-STATUS.md', doc / 'PORT-STATUS.md')
        if name in {'piano', 'camera', 'hidpilot'}:
            copy(ROOT / 'extras/README.md', doc / 'GTK-APPS.md')
        copy(ROOT / 'upstream/shared/licenses', doc / 'licenses/shared')
        copy(ROOT / 'upstream/shared/fonts/OFL.txt', doc / 'licenses/NotoSansSC-OFL.txt')
        copy(ROOT / 'upstream/.deps/mbedtls-2.28.10/LICENSE', doc / 'licenses/MbedTLS-Apache-2.0.txt')
        copy(ROOT / 'upstream/.deps/quickjs-2026-06-04/LICENSE', doc / 'licenses/QuickJS-MIT.txt')
        copy(ROOT / 'upstream/terminal/vendor/libvterm/LICENSE', doc / 'licenses/libvterm-MIT.txt')
        copy(ROOT / 'upstream/terminal/assets/JetBrainsMono-OFL.txt', doc / 'licenses/JetBrainsMono-OFL.txt')
        for app in ('bilibili', 'moonpilot'):
            copy(ROOT / 'upstream' / app / 'licenses', doc / 'licenses' / app)
        copyright_text = 'Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\nUpstream-Name: C1Max applications / TypixDeck native Linux ports\nSource: ' + args.repository + '\n\nThird-party licenses and original notices are in licenses/.\nCorresponding source and build recipes accompany the suite source distribution.\nOriginal C1Max application ownership is retained; no license grant for game images or BIOS is implied.\n'
        write(doc / 'copyright', copyright_text)
        control = f'Package: {package}\nVersion: {args.version}\nArchitecture: {"arm64" if name in NATIVE else "all"}\nMaintainer: TypixDeck <dev@typixnode.com>\nSection: utils\nPriority: optional\nDepends: {depends}\nX-Typix-Compatible-OS: raspios-{codename}\nDescription: TypixDeck {english}\n {summary}\n Complete native application; user content and credentials are not included.\n'
        write(stage / 'DEBIAN/control', control)
        copy(ROOT / 'assets/icons' / (name + '.png'), stage / 'usr/share/icons/hicolor/256x256/apps' / (package + '.png'))
        desktop = f'[Desktop Entry]\nType=Application\nName=Typix {english}\nName[zh_CN]={zh}\nComment={summary}\nExec={executable}\nIcon={package}\nTerminal=false\nCategories={category};\nStartupNotify=true\nStartupWMClass={package}\nX-TypixDeck-FullscreenAppId={package};\n'
        write(stage / 'usr/share/applications' / (package + '.desktop'), desktop)
        # Include all packaged implementation resources in reviewable metadata.
        required = list(dict.fromkeys(required))
        required = [p for p in required if (stage / p.lstrip('/')).is_file()]
        required.extend('/' + str(p.relative_to(stage)) for p in payload.rglob('*') if p.is_file() and '/' + str(p.relative_to(stage)) not in required)
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', '-Zzstd', '-z6', str(stage), str(dist / filename)], check=True)
    digest = hashlib.sha256((dist / filename).read_bytes()).hexdigest()
    metadata = {'schemaVersion': 1, 'repository': args.repository, 'distribution': 'complete-deb', 'application': {
        'id': 'ai.typixdeck.' + name, 'package': package,
        'name': {'zh-CN': zh, 'en': 'Typix ' + english}, 'summary': {'zh-CN': summary},
        'description': {'zh-CN': summary + '。完整原生 Linux 应用；保留用户自己的数据。硬件和服务依赖请见应用说明。'},
        'categories': [category], 'desktopFile': package + '.desktop', 'icon': package, 'runtime': runtime, 'requiredPayload': required,
        'compatibility': {'arch': ['arm64'], 'minMemoryMB': 128 if name not in {'ps1','dosbox'} else 256, 'minFreeDiskMB': 64,
                          'display': ['wayland', 'x11'], 'requiredFeatures': []}},
        'release': {'version': args.version, 'file': 'dist/' + filename, 'sha256': digest},
        'screenshots': screenshot_metadata(name, args.version)}
    for screenshot in metadata['screenshots']:
        copy(ROOT / screenshot['path'], root / screenshot['path'])
    write(root / 'app.json', json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    write(root / 'README.md', f'# Typix {english}\n\n{summary}。\n\n完整 deb、原生界面、用户数据与软件包分离。构建源位于父级 C1Max suite；运行 `python3 tools/build_debs.py --repository OWNER/REPO --apps {name}` 构建该应用。软件包仅兼容官方 Raspberry Pi OS {codename} ARM64。\n\n见随包 PORT-STATUS.md 的具体支持范围和硬件限制。需要媒体服务/ROM/BIOS/USB 节点的功能不会因安装软件包而自动具备。截图来源与验证范围见 app.json，源码渲染和旧版本参考图不表示本次 CM4 实体硬件已验收。\n')
    return {'id': name, 'package': package, 'file': str((dist / filename).relative_to(ROOT)), 'sha256': digest, 'depends': depends, 'compatibleOS': 'raspios-' + codename}


def target_codename(args):
    if args.python_only:
        if not args.target_os:
            raise ValueError('--python-only requires explicit --target-os')
        if set(args.apps) - {'piano', 'hidpilot', 'dosbox', 'ps1'}:
            raise ValueError('--python-only accepts only piano, hidpilot, dosbox and ps1; native apps and held Camera are excluded')
        return args.target_os.removeprefix('raspios-')
    if args.target_os:
        raise ValueError('--target-os is only for explicit --python-only source packaging')
    if platform.system() != 'Linux' or platform.machine() not in {'aarch64', 'arm64'}:
        raise ValueError('Native build and dependency inspection require Linux ARM64')
    os_release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    codename = os_release.get('VERSION_CODENAME', '').strip('"')
    if codename not in {'bookworm', 'trixie'}:
        raise ValueError('Supported build distributions are official Pi OS Bookworm or Trixie')
    return codename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True, help='Explicit source publication owner/repo; not created or uploaded')
    parser.add_argument('--version', default=VERSION)
    parser.add_argument('--apps', nargs='+', choices=list(APPS), default=DEFAULT_APPS)
    parser.add_argument('--python-only', action='store_true', help='Assemble selected architecture-all Python source packages without native compilation; excludes Camera')
    parser.add_argument('--target-os', choices=['raspios-bookworm', 'raspios-trixie'], help='Required target declaration for --python-only; does not assert on-device runtime validation')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('repository must be owner/repo')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[0-9]+', args.version):
        parser.error('version must be a numeric Debian release such as 0.2.0-1')
    if 'camera' in args.apps and args.version != '0.1.0-1':
        parser.error('Camera is held at 0.1.0-1; select it separately with --apps camera --version 0.1.0-1')
    try:
        codename = target_codename(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    (ROOT / 'build').mkdir(exist_ok=True)
    result = [build(name, args, codename) for name in args.apps]
    write(ROOT / 'build/packages.json', json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(f'Built {len(result)} complete debs; no install, upload, signing or publication was performed.')


if __name__ == '__main__':
    main()
