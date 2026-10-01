#!/usr/bin/env python3
"""Headless source UI checks. No GTK display, external services or hardware."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lvgl-library', type=Path, help='Reuse a locally built matching LVGL static library')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/responsive-captures')
    args = parser.parse_args()
    build = ROOT / 'build/native-layout'
    configure = ['cmake', '-S', str(ROOT / 'tests/headless'), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release']
    if args.lvgl_library:
        configure.append('-DTYPIX_LVGL_LIBRARY=' + str(args.lvgl_library.resolve(strict=True)))
    else:
        configure.append('-DTYPIX_LVGL_LIBRARY=')
    subprocess.run(configure, cwd=ROOT, check=True)
    subprocess.run(['cmake', '--build', str(build), '-j2'], cwd=ROOT, check=True)
    for app in ('calculator', 'calendar', 'mail'):
        subprocess.run([str(build / ('layout-' + app)), str(args.output.resolve())], cwd=ROOT, check=True)

if __name__ == '__main__':
    main()
