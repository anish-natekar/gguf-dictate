# Security

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on the Security tab, not a public issue.

Design notes: everything runs locally; there is no network access after install. The tray and dictation
process talk over abstract unix sockets, which any process of the same user (and on the same network namespace) can write
to, so treat the local session as the trust boundary. Runtime files live in a private `0700` directory under `$XDG_RUNTIME_DIR`.
