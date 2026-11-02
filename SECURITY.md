# Security

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on the Security tab, not a public issue.

Design notes: everything runs locally; there is no network access after install. The app is a single process (no IPC sockets), so the
local session is the trust boundary. Runtime files live in a private `0700` directory under `$XDG_RUNTIME_DIR`.

Meeting recordings, transcripts and notes are plain unencrypted files in the user data directory (`meetings/`). Anyone with access to your account can read them; delete a meeting from the Meetings window to remove its folder.
