import shlex
import subprocess


def fetch_rsync_source(url: str, dest: str, credential_ref_token: str = "") -> None:
    """
    Fetch source files from a remote host via rsync over SSH.

    *url* should be an rsync-compatible source path, e.g.:
        ``user@host:/path/to/files`` or ``host:/path``

    The transfer uses ``-az`` (archive + compress) for efficient copies and
    ``--delete`` to mirror the source exactly (files absent from the source
    are removed from *dest*).

    If *credential_ref_token* is non-empty it is treated as a filesystem
    path to an SSH private key and passed to ``ssh -i``.

    Raises subprocess.CalledProcessError on failure.
    """
    cmd = ["rsync", "-az", "--delete"]

    if credential_ref_token:
        cmd += ["-e", f"ssh -i {shlex.quote(credential_ref_token)} -o StrictHostKeyChecking=no"]

    # Ensure trailing slash on source to copy contents (not the directory itself)
    src = url.rstrip("/") + "/"
    # Ensure trailing slash on dest
    dst = dest.rstrip("/") + "/"

    cmd += [src, dst]
    subprocess.run(cmd, check=True, capture_output=True)
