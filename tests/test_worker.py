import platform
from worker.utils.os_exec import run_command, run_python
from worker.executor import execute_job
from worker.utils.completion import evaluate_completion
from worker.utils.python_env import prepare_python_command
from worker.utils.completion import _contains_all, _contains_none


def test_os_exec_echo():
    system = platform.system().lower()
    if system.startswith("win"):
        rc, out, err = run_command("echo hello", shell="cmd")
    else:
        rc, out, err = run_command("echo hello", shell="bash")
    assert rc == 0
    assert "hello" in out.strip().lower()


def test_python_executor_runs_inline_code():
    rc, out, _ = run_python("print('hydra')", interpreter="python3")
    assert rc == 0
    assert "hydra" in out


def test_execute_job_shell_executor():
    job = {"executor": {"type": "shell", "script": "echo hydra-shell", "shell": "bash"}, "timeout": 5}
    rc, out, _ = execute_job(job)
    assert rc == 0
    assert "hydra-shell" in out


def test_execute_job_python_executor():
    job = {"executor": {"type": "python", "code": "print('from python')", "interpreter": "python3"}, "timeout": 5}
    rc, out, _ = execute_job(job)
    assert rc == 0
    assert "from python" in out


def test_execute_job_external_executor():
    binary = "cmd.exe" if platform.system().lower().startswith("win") else "/usr/bin/env"
    args = ["/c", "echo external"] if "cmd" in binary else ["echo", "external"]
    job = {"executor": {"type": "external", "command": binary, "args": args}}
    rc, out, _ = execute_job(job)
    assert rc == 0
    assert "external" in out.lower()


def test_completion_exit_code_evaluation():
    job = {"completion": {"exit_codes": [0]}}
    ok, reason = evaluate_completion(job, 0, "", "")
    assert ok
    assert "criteria" in reason.lower()


def test_completion_stdout_contains():
    job = {"completion": {"exit_codes": [0], "stdout_contains": ["ready"]}}
    ok, reason = evaluate_completion(job, 0, "system ready", "")
    assert ok
    ok, reason = evaluate_completion(job, 0, "no match", "")
    assert not ok
    assert "stdout" in reason.lower()


def test_prepare_python_uv_command():
    executor = {
        "type": "python",
        "interpreter": "python3",
        "environment": {"type": "uv", "python_version": "3.11", "requirements": ["requests"]},
    }
    cmd, cleanup = prepare_python_command(executor, "job-123")
    assert cmd[0:2] == ["uv", "run"]
    assert "--python" in cmd
    assert "--with" in cmd
    assert "requests" in cmd
    assert cmd[-1] == "python3"
    assert cleanup is None


def test_completion_handles_forbidden_tokens():
    job = {
        "completion": {
            "exit_codes": [0],
            "stdout_not_contains": ["forbidden"],
            "stderr_contains": ["needle"],
            "stderr_not_contains": ["panic"],
        }
    }
    ok, reason = evaluate_completion(job, 0, "ok output", "needle present")
    assert ok
    ok, reason = evaluate_completion(job, 0, "forbidden text", "needle present")
    assert not ok and "stdout" in reason.lower()
    ok, reason = evaluate_completion(job, 0, "ok", "nothing here")
    assert not ok and "stderr" in reason.lower()


def test_completion_helpers_are_strict():
    success, reason = _contains_all("abc def", ["abc", "def"])
    assert success
    success, reason = _contains_all("abc", ["abc", "def"])
    assert not success and "missing" in reason.lower()

    success, reason = _contains_none("abc def", ["zzz"])
    assert success
    success, reason = _contains_none("abc def", ["abc"])
    assert not success and "forbidden" in reason.lower()


def test_git_token_injection_https():
    from worker.utils.git import _inject_token_into_url
    url = "https://github.com/user/repo.git"
    result = _inject_token_into_url(url, "mytoken")
    assert "x-oauth-token:mytoken@github.com" in result
    assert result.startswith("https://")


def test_git_token_injection_ssh_passthrough():
    from worker.utils.git import _inject_token_into_url
    url = "git@github.com:user/repo.git"
    result = _inject_token_into_url(url, "mytoken")
    # SSH URLs should pass through unchanged
    assert result == url


def test_git_token_injection_empty_token():
    from worker.utils.git import _inject_token_into_url
    url = "https://github.com/user/repo.git"
    result = _inject_token_into_url(url, "")
    assert result == url


def test_copy_source_directory():
    import tempfile, os
    from worker.utils.copy import fetch_copy_source
    with tempfile.TemporaryDirectory() as src_dir:
        open(os.path.join(src_dir, "run.sh"), "w").write("echo hello")
        sub = os.path.join(src_dir, "subdir")
        os.makedirs(sub)
        open(os.path.join(sub, "data.txt"), "w").write("data")
        with tempfile.TemporaryDirectory() as dest_dir:
            fetch_copy_source(src_dir, dest_dir)
            assert os.path.isfile(os.path.join(dest_dir, "run.sh"))
            assert os.path.isfile(os.path.join(dest_dir, "subdir", "data.txt"))


def test_copy_source_single_file():
    import tempfile, os
    from worker.utils.copy import fetch_copy_source
    with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as f:
        f.write(b"echo hi")
        src_file = f.name
    try:
        with tempfile.TemporaryDirectory() as dest_dir:
            fetch_copy_source(src_file, dest_dir)
            assert os.path.isfile(os.path.join(dest_dir, os.path.basename(src_file)))
    finally:
        os.unlink(src_file)


def test_copy_source_missing_raises():
    import tempfile, pytest
    from worker.utils.copy import fetch_copy_source
    with tempfile.TemporaryDirectory() as dest_dir:
        with pytest.raises(FileNotFoundError):
            fetch_copy_source("/nonexistent/path/that/does/not/exist", dest_dir)


def test_copy_source_rejects_relative_path():
    import tempfile, pytest
    from worker.utils.copy import fetch_copy_source
    with tempfile.TemporaryDirectory() as dest_dir:
        with pytest.raises(ValueError, match="absolute"):
            fetch_copy_source("relative/path", dest_dir)


def test_rsync_source_builds_command(monkeypatch):
    """Verify fetch_rsync_source builds the correct rsync command."""
    import subprocess
    from worker.utils.rsync import fetch_rsync_source

    captured = {}
    def mock_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    fetch_rsync_source("user@host:/data/files", "/tmp/dest")
    assert captured["cmd"][0] == "rsync"
    assert "-az" in captured["cmd"]
    assert "user@host:/data/files/" in captured["cmd"]
    assert "/tmp/dest/" in captured["cmd"]


def test_rsync_source_with_ssh_key(monkeypatch):
    """Verify SSH key is passed via -e flag when credential_ref_token is provided."""
    import subprocess
    from worker.utils.rsync import fetch_rsync_source

    captured = {}
    def mock_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    fetch_rsync_source("user@host:/data/files", "/tmp/dest", credential_ref_token="/path/to/key")
    assert any("/path/to/key" in str(c) for c in captured["cmd"])


def test_git_sparse_clone_calls(monkeypatch):
    """Verify that fetch_git_source with sparse_path uses sparse-checkout commands."""
    import subprocess
    from worker.utils.git import fetch_git_source

    calls = []
    def mock_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    fetch_git_source("https://github.com/org/repo.git", "main", "/tmp/dest", sparse_path="services/my-svc")
    # Should contain git init, git remote add, git sparse-checkout set, git fetch, git checkout
    cmd_strs = [" ".join(c) for c in calls]
    assert any("sparse-checkout" in s for s in cmd_strs), f"Expected sparse-checkout in commands: {cmd_strs}"
    assert any("init" in s for s in cmd_strs), f"Expected git init in commands: {cmd_strs}"


def test_python_executor_uses_temp_file():
    """Large inline code should run without hitting command-line length limits."""
    # Build a script larger than typical ARG_MAX limits would allow via -c
    many_lines = "\n".join(f"x_{i} = {i}" for i in range(500))
    code = many_lines + "\nprint('large-ok')"
    job = {"executor": {"type": "python", "code": code, "interpreter": "python3"}, "timeout": 10}
    rc, out, _ = execute_job(job)
    assert rc == 0
    assert "large-ok" in out


def test_shell_executor_uses_temp_file():
    """Large inline shell script should run without hitting command-line length limits."""
    many_vars = "\n".join(f"V{i}={i}" for i in range(200))
    script = many_vars + "\necho shell-large-ok"
    job = {"executor": {"type": "shell", "script": script, "shell": "bash"}, "timeout": 10}
    rc, out, _ = execute_job(job)
    assert rc == 0
    assert "shell-large-ok" in out


def test_absolute_workdir_treated_as_relative_to_source(monkeypatch, tmp_path):
    """An absolute workdir should be resolved relative to the fetched source root."""
    from worker.utils.copy import fetch_copy_source as real_fetch

    # Create a fake source tree: tmp_path/src/ with subdir/ containing a sentinel file
    src_dir = tmp_path / "src"
    subdir = src_dir / "mysubdir"
    subdir.mkdir(parents=True)
    (subdir / "sentinel.txt").write_text("found-it")

    # Patch fetch_copy_source to copy our fake source into the temp dir
    def _fake_fetch(url, dest):
        real_fetch(str(src_dir), dest)

    monkeypatch.setattr("worker.executor.fetch_copy_source", _fake_fetch)

    # Use an absolute workdir of /mysubdir — should be treated as relative to source root
    job = {
        "source": {"protocol": "copy", "url": str(src_dir)},
        "executor": {
            "type": "shell",
            "script": "cat sentinel.txt",
            "shell": "bash",
            "workdir": "/mysubdir",
        },
        "timeout": 5,
    }
    rc, out, err = execute_job(job)
    assert rc == 0, f"stderr: {err}"
    assert "found-it" in out
