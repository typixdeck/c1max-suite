#!/usr/bin/env python3
"""CM4 Xvfb input verification of real calculator touch/physical key paths."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'docs/screenshots';out.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as temporary:
  state=Path(temporary);data=state/'data';data.mkdir()
  server=subprocess.Popen([str(Path.home()/'.cache/typixdeck-qa-xvfb/root/usr/bin/Xvfb'),'-displayfd','1','-screen','0','800x600x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
  proc=None;d=None
  try:
   display=':'+server.stdout.readline().strip();os.environ.update(DISPLAY=display,GDK_BACKEND='x11',NO_AT_BRIDGE='1')
   import gi;gi.require_version('Gdk','3.0');from gi.repository import Gdk
   Gdk.init([])
   x=C.CDLL(C.util.find_library('X11'));t=C.CDLL(C.util.find_library('Xtst'))
   x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
   x.XCloseDisplay.argtypes=[C.c_void_p];x.XFlush.argtypes=[C.c_void_p]
   x.XStringToKeysym.argtypes=[C.c_char_p];x.XStringToKeysym.restype=C.c_ulong
   x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];x.XKeysymToKeycode.restype=C.c_ubyte
   t.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
   t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
   t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
   d=x.XOpenDisplay(display.encode());assert d
   install=ROOT/'build/qa/install-calculator'
   env=dict(os.environ,HOME=str(state),C1_APPS_ROOT=str(install/'usr/share/typix-calculator'),C1_APPS_DATA=str(data),TYPIX_SMOKE_MS='6000',TYPIX_WINDOWED='1')
   proc=subprocess.Popen([str(install/'usr/bin/typix-calculator')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   time.sleep(1.2)
   def click(px,py):
    t.XTestFakeMotionEvent(d,-1,px,py,0);t.XTestFakeButtonEvent(d,1,True,0);x.XFlush(d);time.sleep(.1);t.XTestFakeButtonEvent(d,1,False,0);x.XFlush(d);time.sleep(.15)
   def key(name):
    code=x.XKeysymToKeycode(d,x.XStringToKeysym(name.encode()));t.XTestFakeKeyEvent(d,code,True,0);t.XTestFakeKeyEvent(d,code,False,0);x.XFlush(d);time.sleep(.15)
   # Preserve-aspect source UI occupies y109..449; real GTK pointer input.
   for point in [(503,358),(730,358),(617,358),(673,415)]:click(*point)
   Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,800,600).savev(str(out/'calculator-touch.png'),'png',[],[])
   # Space clears; source calculator accepts its documented A '+' shortcut.
   for name in ['space','2','a','3','Return']:key(name)
   time.sleep(.2)
   Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,800,600).savev(str(out/'calculator-keyboard.png'),'png',[],[])
   proc.wait(timeout=10);assert proc.returncode==0
  finally:
   if d:x.XCloseDisplay(d)
   if proc and proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=4)
   server.terminate();server.wait(timeout=4)
 print('Calculator pointer and keyboard event screenshots saved; inspect both results for 5.')
if __name__=='__main__':main()
