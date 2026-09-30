#!/usr/bin/env python3
"""Loopback-only Mail protocol and async-job checks. No accounts or real traffic.

Run on the suite build host after building the bundled Mbed TLS libraries:
    python3 tests/test_mail_network.py
"""
from pathlib import Path
import base64
import ctypes as C
import json
import os
import socket
import select
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('TYPIX_SUITE_BUILD',ROOT/'build'))
class Server:
    def __init__(self, handler):
        self.socket=socket.socket(); self.socket.bind(('127.0.0.1',0)); self.socket.listen(2)
        self.port=self.socket.getsockname()[1]; self.stop=threading.Event(); self.errors=[]; self.connection=None
        def run():
            try:
                self.socket.settimeout(3); self.connection,_=self.socket.accept(); self.connection.settimeout(3)
                handler(self.connection,self)
            except (BrokenPipeError,ConnectionError,socket.timeout,ssl.SSLError,OSError): pass
            except BaseException as error: self.errors.append(error)
            finally:
                if self.connection:
                    try:self.connection.close()
                    except OSError:pass
        self.thread=threading.Thread(target=run); self.thread.start()
    def close(self):
        self.stop.set()
        if self.connection:
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.connection.close()
        self.socket.close(); self.thread.join(4)
        assert not self.thread.is_alive(), 'synthetic server failed to stop'
        if self.errors: raise self.errors[0]

def line(sock):
    data=b''
    while not data.endswith(b'\n'):
        chunk=sock.recv(1)
        if not chunk: raise EOFError('client closed')
        data+=chunk
        assert len(data)<150000
    return data.rstrip(b'\r\n')

def expect(sock,value):
    actual=line(sock)
    assert actual==value,(actual,value)

class MailNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='typix-mail-tests-'); cls.work=Path(cls.temp.name)
        cls.binary=cls.work/'mail-test'; cls.cert=cls.work/'cert.pem'; cls.key=cls.work/'key.pem'
        libs=BUILD/'upstream/.deps/mbedtls-2.28.10/library'
        command=['g++','-std=c++17','-O1','-g','-UNDEBUG','-DMAIL_NETWORK_TEST','-Wall','-Wextra','-Werror',
                 '-Wno-misleading-indentation','-I'+str(ROOT/'upstream/mail/src'),'-I'+str(ROOT/'upstream/.deps/mbedtls-2.28.10/include'),
                 str(ROOT/'tests/test_mail_network.cpp'),str(ROOT/'upstream/mail/src/protocol.cpp'),
                 str(libs/'libmbedtls.a'),str(libs/'libmbedx509.a'),str(libs/'libmbedcrypto.a'),'-pthread','-o',str(cls.binary)]
        subprocess.run(command,check=True)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(cls.key),'-out',str(cls.cert),
                        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-addext','basicConstraints=critical,CA:TRUE'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); cls.context.minimum_version=ssl.TLSVersion.TLSv1_2
        cls.context.load_cert_chain(cls.cert,cls.key)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def run_client(self,server,kind='pop',timeout=1800,cancel=-1,implicit=False,host='localhost',trust=True):
        run=subprocess.run([str(self.binary),kind,host,str(server.port),str(self.cert) if trust else '/etc/ssl/certs/ca-certificates.crt',
                            str(timeout),str(cancel),'implicit' if implicit else 'upgrade'],capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(run.stdout); self.assertGreater(result['ticks'],0)
        return result
    def fixture(self,handler,**options):
        server=Server(handler)
        try:return self.run_client(server,**options)
        finally:server.close()
    def tls_pop(self,sock,server,mode):
        sock.sendall(b'+OK synthetic POP\r\n'); expect(sock,b'STLS'); sock.sendall(b'+OK upgrade\r\n')
        if mode=='tls-stall':server.stop.wait(3);return
        sock=self.context.wrap_socket(sock,server_side=True);server.connection=sock
        expect(sock,b'USER fixture@example.test');sock.sendall(b'+OK\r\n');expect(sock,b'PASS synthetic-only')
        if mode=='auth':sock.sendall(b'-ERR fixture rejection\r\n');return
        sock.sendall(b'+OK\r\n');expect(sock,b'LIST');sock.sendall(b'+OK list\r\n')
        if mode=='list-stall':sock.sendall(b'1 100\r\n');server.stop.wait(3);return
        if mode=='list-many':sock.sendall(b''.join(f'{i} 100\r\n'.encode() for i in range(1,10002)));server.stop.wait(2);return
        if mode=='list-invalid':sock.sendall(b'nope\r\n.\r\n');return
        if mode=='list-truncated':sock.sendall(b'1 10\r\n');return
        if mode=='advertised-large':sock.sendall(b'1 262145\r\n.\r\n');server.stop.wait(2);return
        if mode in ('retr-stall','retr-large','retr-lines','retr-truncated'):ids=[1]
        else:ids=list(range(1,11))
        sock.sendall(b''.join(f'{i} 100\r\n'.encode() for i in ids)+b'.\r\n')
        for index in ids[-8:]:
            expect(sock,f'RETR {index}'.encode());sock.sendall(b'+OK body\r\n')
            if mode=='retr-stall':sock.sendall(b'From: fixture\r\n');server.stop.wait(3);return
            if mode=='retr-large':sock.sendall((b'x'*3000+b'\r\n')*100);server.stop.wait(2);return
            if mode=='retr-lines':sock.sendall(b'\r\n'*16385);server.stop.wait(2);return
            if mode=='retr-truncated':sock.sendall(b'From: fixture\r\n');return
            sock.sendall(f'From: sender@example.test\r\nSubject: Fixture {index}\r\nContent-Type: text/plain\r\n\r\nHello\r\n..dot\r\n.\r\n'.encode())
    def tls_smtp(self,sock,server,mode,implicit=False):
        if implicit:sock=self.context.wrap_socket(sock,server_side=True);server.connection=sock
        sock.sendall(b'220 fixture\r\n')
        if not implicit:
            expect(sock,b'EHLO typix.local');sock.sendall(b'250-fixture\r\n250 STARTTLS\r\n')
            expect(sock,b'STARTTLS');sock.sendall(b'220 upgrade\r\n')
            sock=self.context.wrap_socket(sock,server_side=True);server.connection=sock
        expect(sock,b'EHLO typix.local');sock.sendall(b'250-fixture\r\n250 AUTH LOGIN\r\n')
        expect(sock,b'AUTH LOGIN');sock.sendall(b'334 user\r\n');expect(sock,base64.b64encode(b'fixture@example.test'))
        sock.sendall(b'334 password\r\n');expect(sock,base64.b64encode(b'synthetic-only'))
        if mode=='auth':sock.sendall(b'535 fixture rejection\r\n');return
        if mode=='auth-stall':server.stop.wait(3);return
        sock.sendall(b'235 accepted\r\n');expect(sock,b'MAIL FROM:<fixture@example.test>');sock.sendall(b'250 ok\r\n')
        expect(sock,b'RCPT TO:<receiver@example.test>');sock.sendall(b'250 ok\r\n');expect(sock,b'DATA');sock.sendall(b'354 data\r\n')
        payload=[]
        while True:
            value=line(sock)
            if value==b'.':break
            payload.append(value)
        assert b'..dot' in payload and b'Hello' in payload
        if mode=='data-stall':server.stop.wait(3);return
        sock.sendall(b'250 accepted\r\n')
        # Deliberately never answer QUIT. DATA acknowledgement must stay success.
        server.stop.wait(3)
    def test_greeting_timeout_and_cancel(self):
        for kind in ('pop','smtp'):
            for cancel in (-1,60):
                result=self.fixture(lambda s,v:v.stop.wait(3),kind=kind,timeout=220,cancel=cancel)
                self.assertFalse(result['success']);self.assertIn('Cancelled' if cancel>=0 else 'timed out',result['error'])
                self.assertLess(result['elapsed_ms'],650)
    def test_slow_trickle_has_total_deadline(self):
        def trickle(sock,server):
            for _ in range(30):sock.sendall(b'+');server.stop.wait(.045)
        result=self.fixture(trickle,timeout=220)
        self.assertIn('timed out',result['error']);self.assertLess(result['elapsed_ms'],650)
    def test_tls_handshake_cancel(self):
        result=self.fixture(lambda s,v:self.tls_pop(s,v,'tls-stall'),cancel=100)
        self.assertIn('Cancelled',result['error']);self.assertLess(result['elapsed_ms'],650)
    def test_dns_timeout_cancel_and_single_worker_bound(self):
        for kind,cancel in [('dns-timeout',-1),('dns-cancel',50)]:
            result=self.fixture(lambda s,v:v.stop.wait(2),kind=kind,timeout=180,cancel=cancel)
            self.assertFalse(result['success']);self.assertTrue(result['resolver_bounded']);self.assertLess(result['elapsed_ms'],500)
    def test_local_connect_backlog_deadline(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(0)
        fill=socket.socket();fill.settimeout(1);fill.connect(listener.getsockname())
        stub=type('Listener',(),{'port':listener.getsockname()[1]})()
        try:
            result=self.run_client(stub,host='127.0.0.1',timeout=200,cancel=65)
            self.assertIn('Cancelled',result['error']);self.assertLess(result['elapsed_ms'],650)
        finally:fill.close();listener.close()
    def test_line_and_smtp_multiline_limits(self):
        for payload,kind,expected in [(b'+'+b'x'*5000+b'\r\n','pop','4096'),(b'220-more\r\n'*101,'smtp','100 lines'),(b'220-more\r\n250 done\r\n','smtp','expected 220'),(b'2xx bad\r\n','smtp','Invalid SMTP')]:
            result=self.fixture(lambda s,v,p=payload:s.sendall(p),kind=kind)
            self.assertFalse(result['success']);self.assertIn(expected,result['error'])
    def test_pop_success_recent_eight(self):
        result=self.fixture(lambda s,v:self.tls_pop(s,v,'ok'))
        self.assertTrue(result['success'],result);self.assertEqual(result['numbers'],list(range(3,11)))
    def test_pop_list_message_and_auth_limits(self):
        for mode,expected in [('auth','rejected'),('list-many','10000'),('list-invalid','Invalid POP3'),('list-truncated','closed'),('advertised-large','256 KiB'),('retr-large','256 KiB'),('retr-lines','16384'),('retr-truncated','closed')]:
            result=self.fixture(lambda s,v,m=mode:self.tls_pop(s,v,m))
            self.assertFalse(result['success'],(mode,result));self.assertIn(expected,result['error']);self.assertEqual(result['count'],0)
    def test_pop_stall_cancel_after_tls(self):
        for mode in ('list-stall','retr-stall'):
            result=self.fixture(lambda s,v,m=mode:self.tls_pop(s,v,m),cancel=250)
            self.assertIn('Cancelled',result['error']);self.assertLess(result['elapsed_ms'],800)
    def test_smtp_implicit_and_starttls_ehlo(self):
        for implicit in (False,True):
            result=self.fixture(lambda s,v,i=implicit:self.tls_smtp(s,v,'ok',i),kind='smtp',implicit=implicit)
            self.assertTrue(result['success'],result);self.assertLess(result['elapsed_ms'],1400)
    def test_smtp_auth_and_uncertain_delivery(self):
        for mode,cancel,expected in [('auth',-1,'535'),('auth-stall',250,'Cancelled'),('data-stall',350,'delivery status unknown')]:
            result=self.fixture(lambda s,v,m=mode:self.tls_smtp(s,v,m),kind='smtp',cancel=cancel)
            self.assertFalse(result['success']);self.assertIn(expected,result['error'])
    def test_certificate_trust_and_hostname_required(self):
        for host,trust in [('localhost',False),('127.0.0.1',True)]:
            result=self.fixture(lambda s,v:self.tls_pop(s,v,'ok'),host=host,trust=trust)
            self.assertFalse(result['success']);self.assertIn('TLS certificate',result['error'])

@unittest.skipUnless(os.environ.get('TYPIX_MAIL_XVFB'), 'Set TYPIX_MAIL_XVFB for isolated real GTK checks')
class MailUI(unittest.TestCase):
    def test_cancel_retry_and_exit_during_stalled_receive(self):
        x=C.CDLL('libX11.so.6'); xt=C.CDLL('libXtst.so.6')
        x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
        x.XStringToKeysym.argtypes=[C.c_char_p];x.XStringToKeysym.restype=C.c_ulong
        x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];x.XKeysymToKeycode.restype=C.c_uint
        x.XFlush.argtypes=[C.c_void_p];x.XCloseDisplay.argtypes=[C.c_void_p]
        xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        with tempfile.TemporaryDirectory(prefix='typix-mail-ui-') as temp:
            directory=Path(temp);(directory/'data/mail').mkdir(parents=True)
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(2);listener.settimeout(4)
            account={'pop_host':'127.0.0.1','pop_port':str(listener.getsockname()[1]),'username':'fixture@example.test','password':'synthetic-only'}
            (directory/'data/mail/account.json').write_text(json.dumps(account))
            resource=directory/'resources/shared';resource.mkdir(parents=True)
            (resource/'NotoSansSC-Regular.ttf').symlink_to(ROOT/'upstream/shared/fonts/NotoSansSC-Regular.ttf')
            xvfb=subprocess.Popen([os.environ['TYPIX_MAIL_XVFB'],'-displayfd','1','-screen','0','800x600x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            process=connection=display=None
            try:
                self.assertTrue(select.select([xvfb.stdout],[],[],8)[0]);number=xvfb.stdout.readline().strip();self.assertTrue(number.isdigit())
                display=x.XOpenDisplay((':'+number).encode());self.assertTrue(display)
                env=dict(os.environ,DISPLAY=':'+number,GDK_BACKEND='x11',NO_AT_BRIDGE='1',HOME=temp,XDG_DATA_HOME=str(directory/'data'),C1_APPS_DATA=str(directory/'data'),C1_APPS_ROOT=str(directory/'resources'),TYPIX_WINDOWED='1')
                env.pop('TYPIX_SMOKE_MS',None);env.pop('TYPIX_CAPTURE',None)
                process=subprocess.Popen([str(BUILD/'c1max-mail')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                def key(name):
                    code=x.XKeysymToKeycode(display,x.XStringToKeysym(name.encode()));xt.XTestFakeKeyEvent(display,code,1,0);xt.XTestFakeKeyEvent(display,code,0,0);x.XFlush(display)
                time.sleep(1.1);key('r');connection,_=listener.accept();connection.settimeout(.8)
                start=time.monotonic();key('Escape');self.assertEqual(connection.recv(1),b'');self.assertLess(time.monotonic()-start,.8)
                connection.close();connection=None;self.assertIsNone(process.poll())
                time.sleep(.15);key('r');connection,_=listener.accept()
                start=time.monotonic();key('F10');process.wait(timeout=1.2);self.assertLess(time.monotonic()-start,1.2);self.assertEqual(process.returncode,0)
            finally:
                if connection:connection.close()
                listener.close()
                if process and process.poll() is None:process.kill();process.wait()
                if display:x.XCloseDisplay(display)
                xvfb.terminate();xvfb.wait(timeout=3);xvfb.stdout.close()

if __name__=='__main__':unittest.main(verbosity=2)
