"""Real-container tests for `Sandbox`. Each test gets a fresh sandbox and
destroys it afterwards, so `docker ps -a --filter label=dockhand.session`
must be empty when the suite finishes."""

import secrets

import pytest

from dockhand.sandbox import Sandbox, SandboxFileNotFound, SandboxNotFound
from dockhand.sandbox.manager import LABEL_SESSION, docker_client

pytestmark = pytest.mark.docker


@pytest.fixture
def sandbox():
    sb = Sandbox.create(f"test-{secrets.token_hex(3)}")
    try:
        yield sb
    finally:
        sb.destroy()


def test_exec_runs_as_agent_in_workspace(sandbox):
    r = sandbox.exec("echo hello && whoami && pwd && id -u")
    assert r.ok
    assert r.output.splitlines() == ["hello", "agent", "/workspace", "1000"]
    assert r.duration_ms > 0 and not r.timed_out and not r.truncated


def test_exec_nonzero_exit_and_stderr_merged(sandbox):
    r = sandbox.exec("echo out; echo err >&2; exit 3")
    assert r.exit_code == 3
    assert "out" in r.output and "err" in r.output


def test_exec_argv_form_skips_shell(sandbox):
    r = sandbox.exec(["echo", "$HOME", "a b"])  # no shell → $HOME not expanded
    assert r.output == "$HOME a b\n"


def test_exec_timeout_kills_command(sandbox):
    r = sandbox.exec("sleep 30", timeout_s=2)
    assert r.timed_out
    assert r.exit_code == 124
    assert 1500 <= r.duration_ms < 10_000
    assert "timed out" in r.output


def test_exec_output_cap(sandbox):
    r = sandbox.exec("yes | head -c 300000", max_output_bytes=10_000)
    assert r.truncated
    assert len(r.output) < 10_200
    assert "truncated" in r.output


def test_capabilities_dropped_and_no_new_privs(sandbox):
    r = sandbox.exec("grep -E 'CapEff|NoNewPrivs' /proc/self/status")
    assert "CapEff:\t0000000000000000" in r.output
    assert "NoNewPrivs:\t1" in r.output


def test_write_read_roundtrip_with_nested_dirs_and_unicode(sandbox):
    content = "line one\nünïcödé ✓\n\ttabs and 'quotes' and $vars and `backticks`\n"
    sandbox.write_file("src/pkg/module.py", content)
    assert sandbox.read_file("src/pkg/module.py") == content
    assert sandbox.read_file("/workspace/src/pkg/module.py") == content
    owner = sandbox.exec(["stat", "-c", "%U:%G %a", "src/pkg/module.py"])
    assert owner.output.strip() == "agent:agent 644"
    with pytest.raises(SandboxFileNotFound):
        sandbox.read_file("does/not/exist.txt")


def test_diff_includes_new_and_modified_files(sandbox):
    # New, uncommitted file: shows as an addition (thanks to `git add -N`).
    sandbox.write_file("hello.py", "print('hi')\n")
    d = sandbox.diff()
    assert "new file" in d and "+print('hi')" in d
    # Commit it, then modify: now it's a real -/+ change against HEAD.
    assert sandbox.exec("git add -A && git commit -qm base").ok
    sandbox.write_file("hello.py", "print('bye')\n")
    d2 = sandbox.diff()
    assert "-print('hi')" in d2 and "+print('bye')" in d2 and "new file" not in d2
    assert sandbox.diff_stat() == {"files": 1, "insertions": 1, "deletions": 1}
    sandbox.write_file("__pycache__/x.pyc", "junk")  # excluded from stats too
    assert sandbox.diff_stat()["files"] == 1


def test_attach_and_destroy_lifecycle():
    sb = Sandbox.create(f"test-{secrets.token_hex(3)}")
    cid = sb.container_id
    try:
        again = Sandbox.attach(cid)
        assert again.session_id == sb.session_id
        assert again.exec("echo ok").output == "ok\n"
        assert sb.is_alive()
    finally:
        sb.destroy()
    assert not sb.is_alive()
    with pytest.raises(SandboxNotFound):
        Sandbox.attach(cid)


def test_create_replaces_stale_container_with_same_name():
    sid = f"test-{secrets.token_hex(3)}"
    first = Sandbox.create(sid)
    second = Sandbox.create(sid)  # must not raise "name already in use"
    try:
        assert first.container_id != second.container_id
        assert not first.is_alive() and second.is_alive()
    finally:
        second.destroy()


def test_clone_public_repo():
    sid = f"test-{secrets.token_hex(3)}"
    try:
        sb = Sandbox.create(sid, repo_url="https://github.com/octocat/Hello-World")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"clone failed, probably no network from the sandbox: {e}")
    try:
        r = sb.exec("git log --oneline -1 && ls")
        assert r.ok and "README" in r.output
    finally:
        sb.destroy()


def test_bad_repo_url_rejected_before_container_starts():
    with pytest.raises(ValueError):
        Sandbox.create("test-bad", repo_url="git@github.com:foo/bar.git")
    assert not docker_client().containers.list(all=True, filters={"name": "dockhand-test-bad"})


def test_no_leftover_containers():
    """Runs last (alphabetical order not guaranteed, but every fixture cleans
    up); a leak in any test above shows up here."""
    stray = docker_client().containers.list(all=True, filters={"label": f"{LABEL_SESSION}"})
    stray = [c for c in stray if c.name.startswith("dockhand-test-")]
    assert stray == [], [c.name for c in stray]
