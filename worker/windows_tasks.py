"""Windows Task Scheduler helpers for Hydra worker bootstrap.

Uses the ``schtasks`` command-line tool which ships with all modern Windows
editions.  Every public function raises ``RuntimeError`` when called on a
non-Windows platform so that the rest of the bootstrap module can fail fast
with a clear message.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system().lower().startswith("win")

# Maximum length of a Task Scheduler task name (documented limit is 238 chars,
# but we cap earlier for sanity).
_TASK_NAME_MAX_LEN = 200


def _require_windows() -> None:
    """Raise RuntimeError if not running on Windows."""
    if not _IS_WINDOWS:
        raise RuntimeError(
            "Windows Task Scheduler management is only supported on Windows. "
            f"Current platform: {platform.system()!r}. "
            "To run a Hydra worker on Linux/macOS use a systemd service, "
            "launchd plist, or a simple process supervisor instead."
        )


def _quote_arg(value: str) -> str:
    """Return *value* safely quoted for use inside a schtasks /TR argument.

    schtasks /TR receives the full command string as a single argument.  Any
    double-quotes inside the command must be escaped as two consecutive
    double-quotes so that cmd.exe passes them through correctly.
    """
    return value.replace('"', '""')


def build_schtasks_create_command(
    task_name: str,
    command: str,
    working_dir: Optional[str],
    schedule_type: str,
    interval_minutes: int,
    run_as_system: bool,
    description: str,
) -> List[str]:
    """Build the schtasks /Create argument list.

    Parameters
    ----------
    task_name:
        Name of the scheduled task (may include a folder prefix like
        ``\\Hydra\\worker-prod``).
    command:
        Full command string that the task will execute (e.g. the Python
        interpreter followed by bootstrap arguments).
    working_dir:
        Working directory for the task, or ``None`` to use the system default.
    schedule_type:
        One of ``"ONSTART"``, ``"ONCE"``, or ``"MINUTE"``.  Bootstrap tasks
        use ``"ONSTART"`` for the primary trigger and ``"MINUTE"`` for the
        periodic watchdog check.
    interval_minutes:
        For ``"MINUTE"`` schedule, the repetition interval in minutes.
    run_as_system:
        When ``True``, run as ``SYSTEM`` (requires administrator privileges on
        the installing account).
    description:
        Human-readable description stored in the Task Scheduler entry.

    Returns
    -------
    List[str]
        Argument list suitable for ``subprocess.run``.
    """
    quoted_cmd = f'"{_quote_arg(command)}"'

    args: List[str] = [
        "schtasks",
        "/Create",
        "/F",  # Force overwrite if task already exists (idempotent)
        "/TN", task_name,
        "/TR", quoted_cmd,
        "/SC", schedule_type,
        "/RL", "HIGHEST",
    ]

    if schedule_type == "MINUTE":
        args += ["/MO", str(interval_minutes)]

    if run_as_system:
        args += ["/RU", "SYSTEM"]

    # Note: schtasks /Create does not support a working-directory flag.
    # The caller embeds a `cd /d <dir> &&` prefix in the command instead so
    # that the working directory is honoured at execution time.

    # schtasks /Create does not support a /Description flag from the command
    # line; descriptions can only be set via XML import.  We log it for
    # operational reference but do not inject it into the command.
    logger.debug("Task description (not persisted via schtasks CLI): %s", description)

    return args


def build_schtasks_delete_command(task_name: str) -> List[str]:
    """Return the schtasks /Delete argument list for *task_name*."""
    return ["schtasks", "/Delete", "/F", "/TN", task_name]


def build_schtasks_query_command(task_name: str) -> List[str]:
    """Return the schtasks /Query argument list for *task_name*."""
    return ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST"]


def run_schtasks(args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Execute a schtasks command and return the completed process.

    The command is always run with ``shell=False`` to avoid injection risks.
    stdout/stderr are captured as UTF-8 text (with ``errors="replace"``).

    Raises
    ------
    RuntimeError
        On non-Windows platforms.
    subprocess.CalledProcessError
        When the process exits with a non-zero return code.
    """
    _require_windows()
    logger.debug("Running schtasks: %s", args)
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def install_task(
    task_name: str,
    command: str,
    *,
    working_dir: Optional[str] = None,
    schedule_type: str = "ONSTART",
    interval_minutes: int = 5,
    run_as_system: bool = False,
    description: str = "Hydra worker watchdog/bootstrap",
) -> None:
    """Create or update a Windows scheduled task.

    Calling this function multiple times is safe — ``/F`` forces an overwrite,
    making the operation idempotent.

    Parameters
    ----------
    task_name:
        Name of the scheduled task.
    command:
        Full command string for the task action.
    working_dir:
        Optional working directory.  When provided, a ``cd /d "<dir>" && ``
        prefix is prepended to *command* so that the working directory is
        honoured at execution time.
    schedule_type:
        ``"ONSTART"`` (run at system start-up) or ``"MINUTE"`` (periodic).
    interval_minutes:
        Interval for ``"MINUTE"`` schedule type.
    run_as_system:
        Run as SYSTEM account.  Requires the installing user to have admin
        privileges.
    description:
        Human-readable description (logged; not persisted via CLI).

    Raises
    ------
    RuntimeError
        On non-Windows platforms.
    subprocess.CalledProcessError
        When schtasks exits with a non-zero return code.
    """
    _require_windows()

    effective_command = command
    if working_dir:
        # Embed working-directory change into the command so it takes effect
        # regardless of schtasks not having a /WORKDIR flag.
        wd_quoted = working_dir.replace('"', '""')
        effective_command = f'cmd /c "cd /d "{wd_quoted}" && {command}"'

    cmd_args = build_schtasks_create_command(
        task_name=task_name,
        command=effective_command,
        working_dir=None,  # absorbed into command above
        schedule_type=schedule_type,
        interval_minutes=interval_minutes,
        run_as_system=run_as_system,
        description=description,
    )
    result = run_schtasks(cmd_args)
    logger.info("Task %r installed/updated successfully.", task_name)
    if result.stdout:
        logger.debug("schtasks stdout: %s", result.stdout.strip())


def remove_task(task_name: str) -> None:
    """Delete a Windows scheduled task by name.

    If the task does not exist the function logs a warning and returns without
    raising an exception (idempotent removal).

    Raises
    ------
    RuntimeError
        On non-Windows platforms.
    subprocess.CalledProcessError
        When schtasks exits with a non-zero return code for reasons other than
        "task not found".
    """
    _require_windows()
    try:
        run_schtasks(build_schtasks_delete_command(task_name))
        logger.info("Task %r removed successfully.", task_name)
    except subprocess.CalledProcessError as exc:
        # schtasks returns exit code 1 with "ERROR: The system cannot find the
        # file specified." when the task does not exist.
        combined = (exc.output or "") + (exc.stderr or "")
        if "cannot find" in combined.lower() or "does not exist" in combined.lower():
            logger.warning("Task %r not found; nothing to remove.", task_name)
        else:
            raise


def task_exists(task_name: str) -> bool:
    """Return ``True`` if a Windows scheduled task with *task_name* exists.

    Raises
    ------
    RuntimeError
        On non-Windows platforms.
    """
    _require_windows()
    try:
        run_schtasks(build_schtasks_query_command(task_name))
        return True
    except subprocess.CalledProcessError:
        return False
