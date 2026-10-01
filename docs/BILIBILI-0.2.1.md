# Bilibili 0.2.1

The 0.2.0 player sent its User-Agent and Referer only to MPlayer's native HTTP
transport. HTTPS playback uses FFmpeg AVIO in the official Trixie MPlayer, so
those headers were absent from HTTPS video requests. A server that checks them
rejects playback with HTTP 403, although the video list and detail API work.

Version 0.2.1 additionally configures `-lavfstreamopts` with the same User-Agent
and Referer, `tls_verify=1` and the system CA certificate bundle. It retains the
existing native HTTP options and original HTTPS URL. It does not send account
cookies to video CDNs, alter global proxy settings, or download the full video
before playback. Existing login, saved videos, history and UI are unchanged.

An offline regression uses actual production `Player`, API URL validation,
HTTP helpers and Y4M decoding, plus Debian ARM64
`mplayer=2:1.5+svn38674-2`. A loopback-only synthetic clip server rejects missing
headers; the released argument list reproduces 403, while 0.2.1 decodes frames.
Both native HTTP and HTTPS paths send the required headers. HTTPS byte Range
and 302 redirect behavior pass. Wrong-host and untrusted TLS certificates are
rejected before HTTP; no request carries cookies. Display and audio are sinks.

Run the regression only in a disposable root Docker container containing the
repository, its native ARM64 build, that MPlayer version, ffmpeg, openssl and
ca-certificates. It installs a temporary local CA and host aliases in that
container and restores them in `finally`:

```sh
python3 upstream/bilibili/tests/transport_test.py --root /work
```

The correction does not change layout. The app metadata retains the explicitly
labelled 0.2.0 ARM64 GTK screenshot as a UI reference. It does not claim that
screenshot depicts a new CM4 installation. The loopback tests prove the transport
defect and correction; current Bilibili CDN policy, proxy route consistency,
physical CM4 touch/audio and account-specific content require separate on-device
acceptance. Server restrictions and unsupported DASH/live streams remain.

Only the Bilibili package is rebuilt as 0.2.1-1. Build hashes and the exact
environment are recorded in [build provenance](BUILD-PROVENANCE-BILIBILI-0.2.1.json).
