#!/usr/bin/python3
"""Run only synthetic, isolated UI tests; never connect audio, camera or HID."""
import argparse
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvfb", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="c1-extras-xvfb-") as temp:
        server = subprocess.Popen([args.xvfb, "-displayfd", "1", "-screen", "0", "800x600x24", "-nolisten", "tcp"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            if not select.select([server.stdout], [], [], 10)[0]:
                raise RuntimeError("Isolated display did not start")
            display = server.stdout.readline().strip()
            if not display.isdigit():
                raise RuntimeError("Isolated display did not provide a display number")
            os.environ.update(DISPLAY=f":{display}", GDK_BACKEND="x11", NO_AT_BRIDGE="1", XDG_DATA_HOME=temp)
            from PIL import Image
            for name in ("piano", "camera", "hidpilot"):
                os.environ["C1MAX_UI_SCREENSHOT"] = str((output / f"{name}.png").resolve())
                process = subprocess.Popen([sys.executable, str(Path(__file__).parent / f"{name}.py"), "--ui-smoke-test"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    stdout, stderr = process.communicate(timeout=12)
                    (output / f"{name}.log").write_text(stdout + stderr)
                    if process.returncode or "Traceback" in stderr or "TypeError" in stderr:
                        raise RuntimeError(f"{name} UI failed: {stdout}{stderr}")
                    with Image.open(output / f"{name}.png") as screenshot:
                        if screenshot.width > 800 or screenshot.height > 600:
                            raise RuntimeError(f"{name} does not fit 800×600: {screenshot.size}")
                        if not any(low != high for low, high in screenshot.getextrema()):
                            raise RuntimeError(f"{name} screenshot is blank")
                    print(f"{name} isolated UI: PASS", flush=True)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
