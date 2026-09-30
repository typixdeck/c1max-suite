# Mail network execution and limits

Mail runs one background transfer at a time. The GTK/LVGL thread continues drawing and handling input; Escape, the touch Cancel button, and the shared Esc control cancel a transfer. F10/window close cancels before process exit. Workers receive copied account/draft values, never widgets, and publish a complete result via release/acquire completion plus thread join. Only the main thread applies results. Duplicate transfer requests are ignored while busy. Failure or cancellation retains the existing inbox and draft, with an editable account available afterward.

The same monotonic 30-second deadline covers DNS, TCP connect, TLS, authentication, and the entire POP/SMTP transaction. Socket/TLS I/O is nonblocking and polls cancellation/deadline at most every 50 ms; DNS wait checks every 20 ms. A slow peer cannot renew the deadline by trickling bytes. Blocking libc DNS is isolated in at most **one** outstanding resolver thread, owning only a copied host/port and bounded address result. Cancellation releases the transfer without joining that resolver; while it finishes, a new lookup reports a retryable busy error instead of accumulating threads. Process exit does not wait for a stalled resolver. Local CA-file parsing and scheduler latency are outside the poll-interval guarantee.

| Resource | Limit |
|---|---|
| Resolved addresses retained | 8 |
| Protocol line | 4,096 bytes before LF |
| Decrypted wire input / output per transaction | 3 MiB each |
| SMTP multiline reply | 100 lines, each with matching three-digit status and valid separator |
| POP LIST | 10,000 entries, retaining the eight greatest message numbers |
| Received message | 256 KiB and 16,384 lines; advertised oversize also rejected |
| Rendered body | Existing 4,096-byte preview |
| Protocol username/password | 512 bytes each, no CR/LF/NUL |
| Outgoing recipient/From | 254 bytes each |
| Outgoing subject/body | 998 bytes / 64 KiB (existing UI body editor remains 512 bytes) |

Receive results replace the inbox only after the entire bounded operation succeeds. Oversized, malformed, truncated, unauthenticated, or cancelled responses leave the previous inbox untouched. No message data is written to disk by a transfer. Existing account saves use the shared private temporary-file/fsync/rename path; a storage error is now retained visibly rather than overwritten by the settings hint. Account passwords are masked both while viewing and editing.

TLS remains mandatory: Mbed TLS requires a trusted certificate and matching hostname, using `/etc/ssl/certs/ca-certificates.crt`; TLS 1.2 is the minimum. Credentials are never sent before verified TLS. SMTP sends EHLO after both implicit TLS and STARTTLS (also before STARTTLS to negotiate it). No insecure or certificate-bypass option was introduced. A protocol-only TLS mode allows testing standard implicit TLS on an unprivileged loopback port; the GUI keeps its existing port-based 465/995 behavior.

A final SMTP DATA `250` is success even if the server never answers QUIT. Cancellation or disconnect after DATA submission but before confirmation reports **delivery status unknown** and preserves the draft; the user should check the mailbox before retrying. Cancel stops waiting and cannot recall a message already accepted by a server. There is no automatic retry or resend.

## Verification

After building the bundled Mbed TLS libraries on the suite build host:

```sh
python3 tests/test_mail_network.py
# Optional actual GTK test, using a task-owned isolated Xvfb executable:
TYPIX_MAIL_XVFB=/path/to/Xvfb python3 tests/test_mail_network.py
```

The test runner compiles a separate synthetic client against production protocol/async code. It uses only loopback listeners and temporary generated certificates/accounts; no real account is loaded and no public email is sent. Cases cover stalled DNS/connect/greeting/TLS/auth/LIST/RETR, total deadlines under byte trickle, cancellation and duplicate-job suppression, copied worker inputs, SMTP multiline validation, POP listing/message limits/truncation, authentication rejection, certificate trust/hostname rejection, both SMTP TLS modes with required EHLO, accepted DATA with no QUIT acknowledgement, and the eight-message receive path. The optional GTK test verifies Escape closes the stalled socket while the app remains usable, starts a second receive, and exits with F10 while that receive stalls. Test processes/listeners/temp directories are closed in cleanup.

The DNS-delay test hook is compiled only with `MAIL_NETWORK_TEST`; it delays resolution and never bypasses TLS or substitutes successful protocol results. Successful loopback tests demonstrate application behavior, not compatibility with any real provider, OAuth/IMAP/attachments, or delivery through a user account.

Changes stay within the Mail application and its tests/docs. The inherited source and Mbed TLS licenses remain unchanged.
