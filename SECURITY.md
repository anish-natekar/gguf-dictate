# Security

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on the Security tab, not a public issue.

Design notes: everything runs locally; there is no network access after install. The app is a single process (no IPC sockets), so the
local session is the trust boundary. Runtime files live in a private `0700` directory under `$XDG_RUNTIME_DIR`.
