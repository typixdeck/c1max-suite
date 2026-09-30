#!/usr/bin/env python3
"""Extract complete debs and render them on a task-owned Xvfb, never install.

HOME/XDG directories are isolated, and processes are closed in finally.
Screenshots are real CM4 GTK pixels; no physical camera/USB/audio claim.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
XVFB = Path(os.environ.get('TYPIX_XVFB', str(Path.home()/'.cache/typixdeck-qa-xvfb/root/usr/bin/Xvfb')))
NATIVE = {'calculator','calendar','gomoku','terminal','processing','airtune','streamplayer','bilibili','mail','moonpilot'}


def main():
    screenshots = ROOT / 'docs/screenshots'
    screenshots.mkdir(exist_ok=True)
    qa = ROOT / 'build/qa'
    qa.mkdir(exist_ok=True)
    results = []
    with (qa / 'xvfb.log').open('w') as log:
        server = subprocess.Popen([str(XVFB), '-displayfd', '1', '-screen', '0', '800x600x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=log, text=True)
        try:
            display = server.stdout.readline().strip()
            if not display.isdigit():
                raise RuntimeError('Xvfb did not report an isolated display')
            os.environ.update(DISPLAY=':' + display, GDK_BACKEND='x11', NO_AT_BRIDGE='1')
            import gi
            gi.require_version('Gdk', '3.0')
            from gi.repository import Gdk
            Gdk.init([])
            for metadata_path in sorted((ROOT / 'packages').glob('*/app.json')):
                name = metadata_path.parent.name
                meta = json.loads(metadata_path.read_text())
                app = meta['application']
                install = qa / ('install-' + name)
                install.mkdir(exist_ok=True)
                subprocess.run(['dpkg-deb', '-x', str(metadata_path.parent / meta['release']['file']), str(install)], check=True)
                with tempfile.TemporaryDirectory(prefix=name+'-', dir=qa) as state:
                    state = Path(state)
                    for part in ('home', 'data', 'config', 'cache', 'runtime'):
                        (state / part).mkdir(mode=0o700)
                    env = dict(os.environ, HOME=str(state/'home'), XDG_DATA_HOME=str(state/'data'), XDG_CONFIG_HOME=str(state/'config'), XDG_CACHE_HOME=str(state/'cache'), XDG_RUNTIME_DIR=str(state/'runtime'),
                               C1_APPS_ROOT=str(install/'usr/share'/app['package']), C1_APPS_DATA=str(state/'data/c1'), TYPIX_SMOKE_MS='3200', TYPIX_APP_NAME=app['name'].get('en',name), TYPIX_WINDOWED='1')
                    (state/'data/c1').mkdir(mode=0o700)
                    runtime = app['runtime']
                    argv = [str(install/runtime['path'].lstrip('/'))] if runtime['kind']=='native' else ['/usr/bin/python3', str(install/runtime['path'].lstrip('/')), '--ui-smoke-test']
                    path=screenshots/(name+'.png')
                    if path.exists(): path.unlink()
                    own_capture=name not in NATIVE
                    if own_capture: env['C1MAX_UI_SCREENSHOT']=str(path)
                    result = {'id': name, 'started': False, 'screenshot': False}
                    with (qa/(name+'.log')).open('w') as app_log:
                        proc = subprocess.Popen(argv, env=env, stdout=app_log, stderr=subprocess.STDOUT, start_new_session=True)
                        try:
                            if own_capture:
                                deadline=time.monotonic()+10
                                while not path.exists() and proc.poll() is None and time.monotonic()<deadline:
                                    time.sleep(0.05)
                                assert path.exists(), (name,'application did not signal completed rendering')
                            else:
                                time.sleep(1.6)
                            result['started'] = proc.poll() is None
                            if result['started']:
                                pixbuf = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,800,600)
                                if pixbuf is None:
                                    raise RuntimeError('Screenshot unavailable')
                                pixbuf.savev(str(path),'png',[],[])
                            proc.wait(timeout=25)
                            result['exitCode']=proc.returncode
                            with Image.open(path) as rendered:
                                colors=rendered.convert('RGB').getcolors(65536)
                                assert rendered.size==(800,600), (name,rendered.size)
                                assert colors is None or len(colors)>32, (name,'blank screenshot')
                            export=metadata_path.parent/'docs/screenshots'
                            export.mkdir(parents=True,exist_ok=True)
                            shutil.copy2(path,export/(name+'.png'))
                            result['screenshot']=True
                        finally:
                            if proc.poll() is None:
                                os.killpg(proc.pid,signal.SIGTERM)
                                try:
                                    proc.wait(timeout=6)
                                except subprocess.TimeoutExpired:
                                    os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                            result['exitCode']=proc.returncode
                    results.append(result)
                    print(json.dumps(result),flush=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill();server.wait()
            print('Task-owned Xvfb exited:',server.returncode,flush=True)
    (qa/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return 0 if all(r['started'] and r['screenshot'] and r['exitCode']==0 for r in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
