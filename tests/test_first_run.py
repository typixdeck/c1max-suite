#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  assert self.path=='/Users/AuthenticateByName'
  request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  assert request=={'Username':'fixture-user','Pw':'fixture-password'}
  body=b'{"AccessToken":"fixture-token","User":{"Id":"fixture-id"}}'
  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
with tempfile.TemporaryDirectory() as state:
 state=Path(state);binary=state/'typix-streamplayer';home=state/'home';home.mkdir()
 subprocess.run(['g++','-std=c++17','-UNDEBUG','-I'+str(ROOT/'port'),'-I'+str(ROOT/'upstream/shared'),'-I'+str(ROOT/'upstream/include'),'-I'+str(ROOT/'upstream/streamplayer/src'),str(ROOT/'tests/streamplayer_first_run.cpp'),str(ROOT/'build/libc1net.a'),'-pthread','-o',str(binary)],check=True)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(state/'new-data'))
  env.pop('C1_APPS_DATA',None);env.pop('C1_APPS_ROOT',None)
  subprocess.run([str(binary),f'http://127.0.0.1:{server.server_port}'],env=env,check=True,timeout=20)
 finally:server.shutdown();server.server_close();thread.join()
