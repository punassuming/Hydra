from typing import Tuple, Callable, Optional
import tempfile
import shutil
import os
import platform

from .utils.os_exec import run_external, _run_with_callbacks
from .utils.python_env import prepare_python_command
from .utils.git import fetch_git_source


def _detect_shells() -> list[str]:
    """Return list of shells available on this system."""
    found: list[str] = []
    is_win = platform.system().lower().startswith("win")
    candidates = {
        "bash": ["/bin/bash", "--version"] if not is_win else ["bash", "--version"],
        "sh": ["/bin/sh", "--version"] if not is_win else [],
        "cmd": ["cmd", "/c", "echo ok"] if is_win else [],
        "powershell": ["powershell", "-Command", "echo ok"] if is_win else [],
        "pwsh": ["pwsh", "-Command", "echo ok"],
    }
    import subprocess
    for name, cmd in candidates.items():
        if not cmd:
            continue
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            found.append(name)
        except Exception:
            pass
    return found


def _detect_capabilities() -> list[str]:
    """Return list of executor types this worker can handle."""
    caps = ["shell", "external"]
    import subprocess
    # python
    for interp in ("python3", "python"):
        try:
            subprocess.run([interp, "--version"], capture_output=True, timeout=5)
            caps.append("python")
            break
        except Exception:
            pass
    # powershell/pwsh
    for ps in ("pwsh", "powershell"):
        try:
            subprocess.run([ps, "-Command", "echo ok"], capture_output=True, timeout=5)
            if "powershell" not in caps:
                caps.append("powershell")
            break
        except Exception:
            pass
    is_win = platform.system().lower().startswith("win")
    if is_win:
        caps.append("batch")
    # sql - always advertise; driver availability checked at runtime
    caps.append("sql")
    return caps


def _execute_powershell(executor: dict, script: str, args: list, timeout, merged_env, workdir,
                        _with_impersonation, _run_cmd, log_callback_out, log_callback_err):
    """Execute a PowerShell script via pwsh or powershell."""
    shell = executor.get("shell", "pwsh")
    cmd = _with_impersonation([shell, "-NoProfile", "-Command", script] + args)
    if log_callback_out or log_callback_err:
        return _run_cmd(cmd)
    return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)


def _execute_sql(executor: dict, timeout, merged_env, workdir,
                 _run_cmd, log_callback_out, log_callback_err):
    """Execute a SQL query by writing a helper Python script that uses DB-API or pymongo."""
    dialect = executor.get("dialect", "postgres")
    query = executor.get("query", "")
    connection_uri = executor.get("connection_uri") or ""
    database = executor.get("database") or ""

    if not query.strip():
        return 1, "", "sql executor requires a non-empty query"
    if not connection_uri:
        return 1, "", "sql executor requires connection_uri or credential_ref"

    # Build a small Python driver script that connects and runs the query
    if dialect == "mongodb":
        driver_code = (
            "import json, sys\n"
            "try:\n"
            "    from pymongo import MongoClient\n"
            "except ImportError:\n"
            "    print('pymongo is not installed on this worker', file=sys.stderr); sys.exit(1)\n"
            f"client = MongoClient({connection_uri!r})\n"
            f"db = client[{database!r}] if {database!r} else client.get_default_database()\n"
            f"result = db.command({query!r})\n"
            "print(json.dumps(result, default=str))\n"
        )
    else:
        # Use sqlalchemy for relational DBs
        driver_code = (
            "import json, sys\n"
            "try:\n"
            "    from sqlalchemy import create_engine, text\n"
            "except ImportError:\n"
            "    print('sqlalchemy is not installed on this worker', file=sys.stderr); sys.exit(1)\n"
            f"engine = create_engine({connection_uri!r})\n"
            "with engine.connect() as conn:\n"
            f"    result = conn.execute(text({query!r}))\n"
            "    rows = [dict(r._mapping) for r in result]\n"
            "    print(json.dumps(rows, default=str))\n"
        )

    # Write to temp file and execute
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="hydra-sql-")
    try:
        tmp.write(driver_code)
        tmp.close()
        for interp in ("python3", "python"):
            try:
                import subprocess
                subprocess.run([interp, "--version"], capture_output=True, timeout=5)
                cmd = [interp, tmp.name]
                if log_callback_out or log_callback_err:
                    return _run_cmd(cmd)
                return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)
            except Exception:
                continue
        return 1, "", "No Python interpreter found to run SQL driver script"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def execute_job(
    job: dict,
    log_callback_out: Optional[Callable[[str], None]] = None,
    log_callback_err: Optional[Callable[[str], None]] = None,
    kill_event: Optional[object] = None,
) -> Tuple[int, str, str]:
    executor = job.get("executor") or {}
    timeout = job.get("timeout", 0) or None
    env = executor.get("env")
    workdir = executor.get("workdir")
    args = executor.get("args") or []
    impersonate_user = (executor.get("impersonate_user") or "").strip() or None
    kerberos = executor.get("kerberos") or {}
    exec_type = (executor.get("type") or job.get("shell") or "shell").lower()
    job_identifier = job.get("_id") or job.get("id") or "job"
    is_linux = platform.system().lower().startswith("linux")

    if (impersonate_user or kerberos) and not is_linux:
        return 1, "", "impersonation/kerberos executor settings are supported only on Linux workers"

    effective_env = dict(env or {})
    if kerberos.get("ccache"):
        effective_env["KRB5CCNAME"] = str(kerberos.get("ccache"))
    merged_env = effective_env or None

    def _with_impersonation(cmd: list[str]) -> list[str]:
        if impersonate_user:
            return ["sudo", "-n", "-u", impersonate_user, "--"] + cmd
        return cmd

    def _run_cmd(cmd: list[str]) -> Tuple[int, str, str]:
        if log_callback_out or log_callback_err:
            return _run_with_callbacks(
                cmd, timeout, merged_env, workdir,
                on_stdout=log_callback_out,
                on_stderr=log_callback_err,
                kill_event=kill_event,
            )
        return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)

    if kerberos and kerberos.get("principal") and kerberos.get("keytab"):
        kinit_cmd = _with_impersonation(["kinit", "-kt", str(kerberos.get("keytab")), str(kerberos.get("principal"))])
        rc_k, out_k, err_k = _run_cmd(kinit_cmd)
        if rc_k != 0:
            return rc_k, out_k, f"Kerberos init failed: {err_k or out_k}"

    source = job.get("source")
    source_cleanup = None

    if source and source.get("url"):
        tmp_source_dir = tempfile.mkdtemp(prefix=f"hydra-source-{job_identifier}-")
        try:
            fetch_git_source(source["url"], source.get("ref", "main"), tmp_source_dir, token=source.get("token") or "")
            # Determine effective workdir
            # 1. Start at repo root
            base_path = tmp_source_dir
            # 2. If source has a 'path' sub-directory, append it
            if source.get("path"):
                base_path = os.path.join(base_path, source["path"])
            
            # 3. If executor has a workdir:
            #    - if absolute, use it (ignores repo, risky but standard behavior)
            #    - if relative, append to base_path
            if workdir:
                if os.path.isabs(workdir):
                    pass # keep as is
                else:
                    workdir = os.path.join(base_path, workdir)
            else:
                workdir = base_path
            
            def _cleanup_source():
                shutil.rmtree(tmp_source_dir, ignore_errors=True)
            source_cleanup = _cleanup_source

        except Exception as e:
            shutil.rmtree(tmp_source_dir, ignore_errors=True)
            return 1, "", f"Failed to fetch source: {str(e)}"

    try:
        if exec_type == "python":
            code = executor.get("code") or job.get("command", "")
            try:
                command, cleanup = prepare_python_command(executor, job_identifier)
            except Exception as prep_err:
                return 1, "", str(prep_err)
            try:
                cmd_with_code = command + ["-c", code] + args
                if log_callback_out or log_callback_err:
                    rc, out, err = _run_cmd(_with_impersonation(cmd_with_code))
                else:
                    rc, out, err = run_external(
                        binary=_with_impersonation(cmd_with_code)[0],
                        args=_with_impersonation(cmd_with_code)[1:],
                        timeout=timeout,
                        env=merged_env,
                        workdir=workdir,
                    )
                return rc, out, err
            finally:
                if cleanup:
                    cleanup()
        if exec_type == "external":
            binary = executor.get("command") or job.get("command", "")
            cmd = _with_impersonation([binary] + args)
            if log_callback_out or log_callback_err:
                return _run_cmd(cmd)
            return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)
        if exec_type == "batch":
            script = executor.get("script") or job.get("command", "")
            shell = executor.get("shell", "cmd")
            cmd = _with_impersonation(["cmd", "/c", script] if shell == "cmd" else [shell, "-c", script])
            if log_callback_out or log_callback_err:
                return _run_cmd(cmd)
            return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)
        if exec_type == "powershell":
            script = executor.get("script") or job.get("command", "")
            return _execute_powershell(
                executor, script, args, timeout, merged_env, workdir,
                _with_impersonation, _run_cmd, log_callback_out, log_callback_err,
            )
        if exec_type == "sql":
            return _execute_sql(
                executor, timeout, merged_env, workdir,
                _run_cmd, log_callback_out, log_callback_err,
            )

        # default shell executor
        script = executor.get("script") or job.get("command", "")
        shell = executor.get("shell", job.get("shell", "bash"))
        cmd = _with_impersonation(["/bin/bash", "-lc", script] if shell == "bash" else [shell, "-c", script])
        if log_callback_out or log_callback_err:
            return _run_cmd(cmd)
        return run_external(binary=cmd[0], args=cmd[1:], timeout=timeout, env=merged_env, workdir=workdir)
    finally:
        if source_cleanup:
            source_cleanup()
