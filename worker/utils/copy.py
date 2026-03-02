import os
import shutil


def fetch_copy_source(src: str, dest: str) -> None:
    """
    Copy a local file or directory to the destination directory.

    If *src* is a file, the file is copied into *dest* (preserving the
    filename).  If *src* is a directory, the entire tree is copied into
    *dest*.  Raises FileNotFoundError when *src* does not exist.

    Security note: *src* is resolved from the job definition and is
    therefore operator-controlled.  The worker process must have read
    access to the path.  Restrict worker file-system permissions
    appropriately to limit access to sensitive paths.
    """
    if not os.path.exists(src):
        raise FileNotFoundError(f"Copy source path not found: {src}")

    if os.path.isfile(src):
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(src, os.path.join(dest, os.path.basename(src)))
    elif os.path.isdir(src):
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        raise ValueError(f"Copy source is not a regular file or directory: {src}")
