#!/usr/bin/env python3
"""Exercise production Bilibili YUV decode/composition with synthetic local MP4.

MPlayer is supplied from an isolated apt extraction or the distro installation.
No network/account/media service, audio device or installed desktop is used.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    qa=ROOT/'build/media-qa';qa.mkdir(parents=True,exist_ok=True)
    player=ROOT/'qa-deps/root/usr/bin/mplayer'
    libs=ROOT/'qa-deps/root/usr/lib/aarch64-linux-gnu'
    xvfb=Path(os.environ.get('TYPIX_XVFB',str(Path.home()/'.cache/typixdeck-qa-xvfb/root/usr/bin/Xvfb')))
    with tempfile.TemporaryDirectory(dir=qa) as state:
        state=Path(state);home=state/'home';home.mkdir(mode=0o700)
        data=state/'data';(data/'bilibili').mkdir(parents=True,mode=0o700)
        clip=state/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=15','-t','3','-c:v','libx264','-pix_fmt','yuv420p','-an',str(clip)],check=True)
        server=subprocess.Popen([str(xvfb),'-displayfd','1','-screen','0','800x600x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        proc=None
        try:
            display=server.stdout.readline().strip();assert display.isdigit()
            install=ROOT/'build/qa/install-bilibili'
            env=dict(os.environ,HOME=str(home),DISPLAY=':'+display,GDK_BACKEND='x11',NO_AT_BRIDGE='1',C1_APPS_ROOT=str(install/'usr/share/typix-bilibili'),C1_APPS_DATA=str(data),
                     C1_BILI_QA_LOCAL=str(clip),C1_BILI_SILENT='1',TYPIX_MPLAYER=str(player),LD_LIBRARY_PATH=str(libs),TYPIX_SMOKE_MS='5500',TYPIX_WINDOWED='1')
            with (qa/'decode.log').open('w') as log:
                proc=subprocess.Popen([str(ROOT/'build/c1max-bilibili')],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                proc.wait(timeout=18)
            text=(qa/'decode.log').read_text()
            frames=[int(x) for x in re.findall(r'frames=(\d+)',text)]
            result={'exitCode':proc.returncode,'decodedFrames':max(frames,default=0),'fixture':'locally generated 320x180 H264 test pattern','physicalAudio':False}
            (qa/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
            assert proc.returncode==0 and result['decodedFrames']>=15,text
        finally:
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            server.terminate()
            try:server.wait(timeout=4)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
