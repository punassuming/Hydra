from typing import Tuple, Callable, Optional
import tempfile
import shutil
import os
import platform

from .utils.os_exec import run_external, _run_with_callbacks
from .utils.python_env import prepare_python_command
from .utils.git import fetch_git_source


def execute_job(
    job: dict,
    log_callback_out: Optional[Callable[[str], None]] = None,
    log_callback_err: Optional[Callable[[str], None]] = None,
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
                cmd, timeout, merged_env, workdir, on_stdout=log_callback_out, on_stderr=log_callback_err
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
            fetch_git_source(source["url"], source.get("ref", "main"), tmp_source_dir)
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
