#!/usr/bin/env python3
"""Real Debian ARM64 MPlayer HTTP/HTTPS header regression, entirely offline.

Run only in a disposable Docker container containing the repository, its native
ARM64 build, mplayer, ffmpeg, openssl and ca-certificates. The test installs a
temporary local CA and two loopback-only hosts in that container, restores them
in finally, and removes all test media/certificates. It has no user credentials,
CDN URLs, network API calls, physical display or audio device access.
"""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
import threading


def run(args, **kwargs):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, **kwargs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    args=parser.parse_args();root=args.root.resolve()
    if not Path('/.dockerenv').exists() or os.geteuid()!=0:
        raise SystemExit('Use a disposable root Docker container; never run on a device/host.')
    version=run(['dpkg-query','-W','-f=${Version}','mplayer']).stdout
    if version!='2:1.5+svn38674-2':
        raise SystemExit('This regression requires the CM4 Debian Trixie MPlayer version.')
    hosts=Path('/etc/hosts');original_hosts=hosts.read_bytes()
    ca_path=Path('/usr/local/share/ca-certificates/typix-bili-transport-qa.crt')
    if ca_path.exists():raise SystemExit('Refusing to overwrite an existing CA fixture.')
    servers=[];threads=[];observations=[];results={}
    host='fixture.bilivideo.com';bad_host='wrong-name.bilivideo.com'
    with tempfile.TemporaryDirectory(prefix='typix-bili-transport-') as temporary:
        temp=Path(temporary)
        try:
            hosts.write_bytes(original_hosts+b'\n127.0.0.1 '+host.encode()+b' '+bad_host.encode()+b'\n')
            run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                 '-subj','/CN=Typix disposable transport CA','-keyout',str(temp/'ca.key'),'-out',str(temp/'ca.crt')])
            run(['openssl','req','-new','-newkey','rsa:2048','-nodes',
                 '-subj','/CN='+host,'-keyout',str(temp/'server.key'),'-out',str(temp/'server.csr')])
            (temp/'extensions').write_text('subjectAltName=DNS:'+host+'\nbasicConstraints=CA:FALSE\n')
            run(['openssl','x509','-req','-in',str(temp/'server.csr'),'-CA',str(temp/'ca.crt'),
                 '-CAkey',str(temp/'ca.key'),'-CAcreateserial','-days','1','-extfile',str(temp/'extensions'),'-out',str(temp/'server.crt')])
            shutil.copyfile(temp/'ca.crt',ca_path);run(['update-ca-certificates'])
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=15',
                 '-t','20','-c:v','libx264','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(temp/'clip.mp4')])
            media=(temp/'clip.mp4').read_bytes()
            class Handler(BaseHTTPRequestHandler):
                protocol_version='HTTP/1.1'
                def log_message(self,*_):pass
                def do_GET(self):
                    row={'path':self.path,'ua':self.headers.get('User-Agent')=='Mozilla/5.0',
                         'referer':self.headers.get('Referer')=='https://www.bilibili.com/',
                         'range':bool(re.fullmatch(r'bytes=\d+-\d*',self.headers.get('Range',''))),
                         'cookie':bool(self.headers.get('Cookie'))}
                    observations.append(row)
                    if not row['ua'] or not row['referer']:
                        self.send_response(403);self.send_header('Content-Length','0');self.end_headers();return
                    if self.path=='/redirect.mp4':
                        self.send_response(302);self.send_header('Location','https://'+host+'/clip.mp4')
                        self.send_header('Content-Length','0');self.end_headers();return
                    match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers.get('Range',''))
                    start=int(match[1]) if match else 0
                    end=min(int(match[2]) if match and match[2] else len(media)-1,len(media)-1)
                    body=media[start:end+1]
                    self.send_response(206 if match else 200)
                    self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes')
                    self.send_header('Content-Length',str(len(body)))
                    if match:self.send_header('Content-Range',f'bytes {start}-{end}/{len(media)}')
                    self.end_headers()
                    with contextlib.suppress(BrokenPipeError,ConnectionResetError):self.wfile.write(body)
            for port in (80,443):
                server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
                if port==443:
                    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.load_cert_chain(temp/'server.crt',temp/'server.key')
                    server.socket=ctx.wrap_socket(server.socket,server_side=True)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                servers.append(server);threads.append(thread)
            # A display sink avoids GTK, display devices and framebuffer setup.
            (temp/'display.hpp').write_text('#pragma once\n#include <cstdint>\nnamespace screen {extern bool playing,tap;uint32_t tick();bool video_begin();void video_frame(const uint32_t*,int,int,int,int);void video_refresh(bool);void video_end();}\n')
            binary=temp/'probe'
            run(['g++','-std=c++17','-O1','-I'+str(temp),'-I'+str(root/'port'),
                 '-I'+str(root/'upstream/shared'),'-I'+str(root/'upstream/include'),
                 '-I'+str(root/'upstream/streamplayer/src'),'-I'+str(root/'upstream/bilibili/src'),
                 '-I'+str(root/'upstream/.deps/mbedtls-2.28.10/include'),
                 str(root/'upstream/bilibili/src/player.cpp'),str(root/'upstream/bilibili/src/api.cpp'),
                 str(root/'upstream/shared/net.cpp'),str(root/'upstream/bilibili/tests/transport_probe.cpp'),
                 str(root/'build/upstream/.deps/mbedtls-2.28.10/library/libmbedcrypto.a'),'-pthread','-o',str(binary)])
            # Recreate the released argv by dropping only the new transport flag.
            # The same production Player / actual MPlayer must reproduce 403.
            wrapper=temp/'legacy-player'
            wrapper.write_text('#!/usr/bin/python3\nimport os,sys\na=sys.argv[1:]\ni=a.index("-lavfstreamopts");del a[i:i+2]\nos.execv("/usr/bin/mplayer",["mplayer"]+a)\n');wrapper.chmod(0o700)
            run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                 '-subj','/CN='+host,'-addext','subjectAltName=DNS:'+host,
                 '-keyout',str(temp/'untrusted.key'),'-out',str(temp/'untrusted.crt')])
            for label,url,expect,player in [
                ('legacy_https','https://'+host+'/clip.mp4','403',str(wrapper)),
                ('fixed_https','https://'+host+'/clip.mp4','decode','/usr/bin/mplayer'),
                ('fixed_http','http://'+host+'/clip.mp4','decode','/usr/bin/mplayer'),
                ('https_redirect','https://'+host+'/redirect.mp4','decode','/usr/bin/mplayer'),
                ('tls_wrong_name','https://'+bad_host+'/clip.mp4','reject','/usr/bin/mplayer'),
                ('tls_untrusted','https://'+host+'/clip.mp4','reject','/usr/bin/mplayer')]:
                if label=='tls_untrusted':ctx.load_cert_chain(temp/'untrusted.crt',temp/'untrusted.key')
                begin=len(observations);data=temp/label;data.mkdir(mode=0o700)
                env=dict(os.environ,C1_APPS_DATA=str(data),TYPIX_MPLAYER=player)
                # Proxy settings cannot send the loopback fixture elsewhere.
                for key in list(env):
                    if key.lower().endswith('_proxy'):env.pop(key)
                outcome=run([str(binary),url,expect],env=env,timeout=18)
                rows=observations[begin:]
                results[label]={'passed':True,'decoded':'decoded=1' in outcome.stdout,
                                'requests':len(rows),'headersCorrect':bool(rows) and all(x['ua'] and x['referer'] for x in rows),
                                'rangeSeen':any(x['range'] for x in rows),'cookiesSent':any(x['cookie'] for x in rows)}
                if label=='legacy_https':assert rows and not results[label]['headersCorrect']
                elif expect=='decode':
                    assert rows and results[label]['headersCorrect'],(label,results[label])
                    # Native MPlayer HTTP may initially fetch the complete file;
                    # FFmpeg HTTPS starts with a byte Range, including redirect.
                    if url.startswith('https:'):assert results[label]['rangeSeen'],label
                else:assert not rows,'TLS hostname failure must occur before HTTP'
                assert not results[label]['cookiesSent']
            print(json.dumps({'mplayer':version,'fixture':'loopback synthetic MP4; production Player/Y4M',
                              'cases':results},indent=2))
        finally:
            for server in servers:server.shutdown();server.server_close()
            for thread in threads:thread.join(timeout=2)
            hosts.write_bytes(original_hosts)
            if ca_path.exists():ca_path.unlink();run(['update-ca-certificates','--fresh'])


if __name__=='__main__':main()
