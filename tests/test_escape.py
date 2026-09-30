#!/usr/bin/env python3
"""Real GTK signal routes plus production app handlers; isolated Xvfb/loopback."""
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
ROOT = Path(__file__).resolve().parents[1]
stop = threading.Event()
class Stalled(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(.1)
        while not stop.is_set():
            try:
                if not self.request.recv(4096): break
            except TimeoutError: pass
class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
with tempfile.TemporaryDirectory() as temporary:
    state = Path(temporary)
    (state/'processing').mkdir()
    xvfb = subprocess.Popen([os.environ.get('TYPIX_XVFB', str(Path.home()/'.cache/typixdeck-qa-xvfb/root/usr/bin/Xvfb')), '-displayfd', '1', '-screen', '0', '800x600x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    server = Server(('127.0.0.1', 0), Stalled)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ, DISPLAY=':'+xvfb.stdout.readline().strip(), GDK_BACKEND='x11', NO_AT_BRIDGE='1', HOME=str(state), TYPIX_WINDOWED='1', C1_APPS_DATA=str(state), C1_APPS_ROOT=str(ROOT/'upstream'))
        for app in ['processing', 'airtune', 'streamplayer']:
            subprocess.run([str(ROOT/'build'/('c1max-escape-'+app)), f'http://127.0.0.1:{server.server_address[1]}'], env=env, check=True, timeout=15)
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join()
        xvfb.terminate(); xvfb.wait(timeout=4)
