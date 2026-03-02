import subprocess
import shutil
import os
from urllib.parse import urlparse, urlunparse


def _inject_token_into_url(url: str, token: str) -> str:
    """Inject a personal access token into an HTTPS git URL for authentication."""
    if not token:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        # SSH or other protocol — cannot inject token into URL
        return url
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    # Use token as username with 'x-oauth-token' convention (works for GitHub, GitLab, etc.)
    netloc = f"x-oauth-token:{token}@{netloc}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def fetch_git_source(url: str, ref: str, dest: str, token: str = "") -> None:
    """
    Clones a git repository to the destination directory and checks out the reference.

    Uses a shallow clone (--depth 1) when ref looks like a branch/tag name for
    efficiency.  If token is provided it is injected into the HTTPS URL for
    private-repository authentication (personal access token / OAuth token).
    """
    clone_url = _inject_token_into_url(url, token) if token else url

    # Attempt a shallow clone first (faster for large repos).  Fall back to a
    # full clone if the shallow clone fails (e.g. when ref is a commit SHA).
    cmd_shallow = ["git", "clone", "-q", "--depth", "1", clone_url, dest]
    result = subprocess.run(cmd_shallow, capture_output=True)
    if result.returncode != 0:
        # Remove any partial clone before retrying
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
        cmd_clone = ["git", "clone", "-q", clone_url, dest]
        subprocess.run(cmd_clone, check=True)

    # Checkout the requested ref
    if ref:
        cmd_checkout = ["git", "checkout", ref]
        subprocess.run(cmd_checkout, cwd=dest, check=True)
