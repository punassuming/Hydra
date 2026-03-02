import subprocess


def fetch_rsync_source(url: str, dest: str, credential_ref_token: str = "") -> None:
    """
    Fetch source files from a remote host via rsync over SSH.

    *url* should be an rsync-compatible source path, e.g.:
        ``user@host:/path/to/files`` or ``host:/path``

    The transfer uses ``-az`` (archive + compress) for efficient copies.
    If *credential_ref_token* is non-empty it is written to a temporary file
    and passed as the SSH identity key via ``-e 'ssh -i ...'``.  This
    supports private-key-based authentication for remote hosts.

    Raises subprocess.CalledProcessError on failure.
    """
    cmd = ["rsync", "-az", "--delete"]

    if credential_ref_token:
        # credential_ref_token is treated as an SSH private key path
        cmd += ["-e", f"ssh -i {credential_ref_token} -o StrictHostKeyChecking=no"]

    # Ensure trailing slash on source to copy contents (not the directory itself)
    src = url.rstrip("/") + "/"
    # Ensure trailing slash on dest
    dst = dest.rstrip("/") + "/"

    cmd += [src, dst]
    subprocess.run(cmd, check=True, capture_output=True)
