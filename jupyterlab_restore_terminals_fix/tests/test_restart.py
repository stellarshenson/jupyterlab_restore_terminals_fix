"""ACC-REOPEN-1 (functional): a real server restart re-creates the saved terminal.

This is the primary path end to end at the server boundary: a terminal in a
subfolder is saved, the server is stopped, a new server starts, and the
terminal is running again in the same folder before a browser connects.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import suppress
from pathlib import Path

import pytest

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")

TOKEN = "restart-test-token"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(url: str, method: str = "GET", body: dict | None = None, timeout: float = 5):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"token {TOKEN}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read() or b"null")


def _start_server(port: int, root: Path, workspaces: Path, env: dict, log) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "jupyter",
            "lab",
            "--no-browser",
            f"--ServerApp.port={port}",
            "--ServerApp.port_retries=0",
            "--ServerApp.open_browser=False",
            f"--ServerApp.root_dir={root}",
            f"--LabApp.workspaces_dir={workspaces}",
            "--ServerApp.allow_unauthenticated_access=True",
            f"--IdentityProvider.token={TOKEN}",
            "--ServerApp.log_level=WARN",
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def _wait_for_server(base: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = _request(base + "/api/terminals", timeout=2)
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise AssertionError(f"server did not answer on {base}")


def _terminal_names(base: str) -> list[str]:
    _, payload = _request(base + "/api/terminals")
    return [terminal["name"] for terminal in payload]


@linux_only
def test_restart_recreates_saved_terminal(tmp_path):
    """ACC-REOPEN-1: a restart re-creates the terminal in its saved subfolder."""
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    workspaces = tmp_path / "workspaces"
    data = tmp_path / "data"
    config = tmp_path / "config"
    runtime = tmp_path / "runtime"
    for folder in (workspaces, data, config, runtime):
        folder.mkdir()

    repo_root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": str(repo_root),
        "JUPYTER_DATA_DIR": str(data),
        "JUPYTER_CONFIG_DIR": str(config),
        "JUPYTER_RUNTIME_DIR": str(runtime),
    }
    log_path = tmp_path / "server.log"
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = None
    with open(log_path, "w") as log:
        try:
            proc = _start_server(port, root, workspaces, env, log)
            _wait_for_server(base)

            status, _ = _request(
                base + "/api/terminals", "POST", {"name": "1", "cwd": str(sub)}
            )
            assert status in (200, 201)
            assert "1" in _terminal_names(base)

            status, payload = _request(
                base + "/jupyterlab-restore-terminals-fix/state",
                "POST",
                {"names": ["1"]},
            )
            assert status == 200
            assert payload["saved"] == {"1": os.path.realpath(sub)}

            _stop_server(proc)
            proc = None

            proc = _start_server(port, root, workspaces, env, log)
            _wait_for_server(base)

            # The extension's startup timer fires 1 s after load, before the
            # server answers; a 3 s poll catches a regression to a later timer
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if "1" in _terminal_names(base):
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("saved terminal was not re-created within 3 s")

            status, payload = _request(
                base + "/jupyterlab-restore-terminals-fix/cwd/1"
            )
            assert status == 200
            assert payload["cwd"] == os.path.realpath(sub)
        except BaseException:
            print(log_path.read_text()[-4000:])
            raise
        finally:
            if proc is not None:
                _stop_server(proc)
