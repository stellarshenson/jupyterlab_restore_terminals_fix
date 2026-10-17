import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import suppress
from types import SimpleNamespace

import pytest
from jupyter_core.paths import jupyter_data_dir

import jupyterlab_restore_terminals_fix
from jupyterlab_restore_terminals_fix import routes


linux_only = pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")

SIBLINGS_HELPER = """
import subprocess, sys, time

sleeper = subprocess.Popen(["sleep", "60"], cwd=sys.argv[1])
# read blocks on the pipe this process holds open and never writes
shell = subprocess.Popen(["sh", "-c", "read line"], cwd=sys.argv[2], stdin=subprocess.PIPE)
time.sleep(60)
"""

FORKING_THREAD_HELPER = """
import subprocess, threading, time

def fork_and_stay():
    child = subprocess.Popen(["sleep", "60"])
    print(child.pid, flush=True)
    # The forking thread must stay alive, or the kernel reparents the child
    time.sleep(60)

threading.Thread(target=fork_and_stay).start()
time.sleep(60)
"""


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out waiting for helper processes"
        time.sleep(0.01)


def _read_children(pid, tid):
    try:
        with open(f"/proc/{pid}/task/{tid}/children") as f:
            return [int(c) for c in f.read().split()]
    except OSError:
        return []


def _kill_group(proc):
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _block_subprocess(monkeypatch):
    calls = []

    def recorder(args, *a, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(subprocess, "run", recorder)
    monkeypatch.setattr(subprocess, "Popen", recorder)
    return calls


def _fake_manager(pids):
    created = []
    return SimpleNamespace(
        terminals={
            name: SimpleNamespace(ptyproc=SimpleNamespace(pid=pid))
            for name, pid in pids.items()
        },
        created=created,
        create=lambda **kwargs: created.append(kwargs),
    )


def _inject_manager(monkeypatch, jp_serverapp, pids):
    manager = _fake_manager(pids)
    monkeypatch.setitem(jp_serverapp.web_app.settings, "terminal_manager", manager)
    return manager


def _inject_terminal(monkeypatch, jp_serverapp, pid):
    return _inject_manager(monkeypatch, jp_serverapp, {"t1": pid})


def _fake_server(manager, server_root):
    settings = {"terminal_manager": manager, "server_root_dir": str(server_root)}
    return SimpleNamespace(
        web_app=SimpleNamespace(settings=settings),
        log=logging.getLogger(__name__),
    )


def _write_workspace(workspaces_dir, slug, terminal_names):
    data = {f"terminal:{name}": {"data": {"name": name}} for name in terminal_names}
    data["layout-restorer:data"] = {"main": {"dock": None}}
    path = workspaces_dir / f"{slug}.jupyterlab-workspace"
    path.write_text(json.dumps({"data": data, "metadata": {"id": slug}}))


def _use_workspaces_dir(monkeypatch, jp_serverapp, workspaces_dir):
    monkeypatch.setitem(
        jp_serverapp.web_app.settings,
        "restore_terminals_fix_workspaces_dir",
        str(workspaces_dir),
    )


def _sleeper(cwd):
    return subprocess.Popen(["sleep", "60"], cwd=cwd, start_new_session=True)


async def _post_state(jp_fetch, names):
    response = await jp_fetch(
        "jupyterlab-restore-terminals-fix", "state",
        method="POST", body=json.dumps({"names": names})
    )
    assert response.code == 200
    return json.loads(response.body)["saved"]


async def _await_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out waiting for the terminal"
        await asyncio.sleep(0.05)


async def _create_terminal(jp_fetch, name, cwd):
    await jp_fetch(
        "api", "terminals",
        method="POST", body=json.dumps({"name": name, "cwd": str(cwd)})
    )


async def _delete_terminal(jp_fetch, manager, name):
    await jp_fetch("api", "terminals", name, method="DELETE")
    # The manager drops the name once the pty reports end of file
    await _await_until(lambda: name not in manager.terminals)


async def _terminate_all(manager):
    for name in list(manager.terminals):
        if name in manager.terminals:
            await manager.terminate(name, force=True)
    await _await_until(lambda: not manager.terminals)


@pytest.fixture
def jp_server_config(jp_server_config):
    # A plain sh keeps real terminals fast and free of login profile scripts
    jp_server_config["ServerApp"]["terminado_settings"] = {
        "shell_command": ["/bin/sh"]
    }
    return jp_server_config


@pytest.fixture
def no_startup_prepopulate(monkeypatch):
    # The extension's 1 s startup timer would re-create a deleted terminal
    # in the middle of a test
    monkeypatch.setattr(
        jupyterlab_restore_terminals_fix,
        "prepopulate_terminals",
        lambda server_app: None,
    )


async def test_cwds_endpoint(jp_fetch):
    response = await jp_fetch("jupyterlab-restore-terminals-fix", "cwds")
    assert response.code == 200
    payload = json.loads(response.body)
    assert "terminals" in payload
    assert isinstance(payload["terminals"], list)


async def test_cwd_not_found(jp_fetch):
    response = await jp_fetch(
        "jupyterlab-restore-terminals-fix", "cwd", "nonexistent",
        raise_error=False
    )
    assert response.code == 404
    payload = json.loads(response.body)
    assert "error" in payload
    assert payload["error"] == "not found"


@linux_only
async def test_state_post_starts_no_subprocess(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-RECORD-17: looking up terminal folders on Linux starts no subprocess."""
    assert jupyter_data_dir() == str(jp_data_dir)
    helper = subprocess.Popen(
        ["sh", "-c", "sleep 60 & sleep 60 & wait"],
        cwd=tmp_path,
        start_new_session=True,
    )
    try:
        _wait_until(lambda: len(_read_children(helper.pid, helper.pid)) == 2)
        _inject_terminal(monkeypatch, jp_serverapp, helper.pid)
        calls = _block_subprocess(monkeypatch)

        response = await jp_fetch(
            "jupyterlab-restore-terminals-fix", "state",
            method="POST", body=json.dumps({"names": ["t1"]})
        )

        assert calls == []
        payload = json.loads(response.body)
        assert payload == {"saved": {"t1": os.path.realpath(tmp_path)}}
    finally:
        _kill_group(helper)


@linux_only
def test_direct_children_include_thread_forked_child(monkeypatch):
    """ACC-RECORD-14: a child forked by a non-main thread is found."""
    with subprocess.Popen(
        [sys.executable, "-c", FORKING_THREAD_HELPER],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as helper:
        try:
            sleep_pid = int(helper.stdout.readline())
            _wait_until(lambda: os.path.exists(f"/proc/{sleep_pid}"))
            # The main thread's children file must not list it, or the test proves nothing
            assert sleep_pid not in _read_children(helper.pid, helper.pid)
            _block_subprocess(monkeypatch)

            assert sleep_pid in routes._get_direct_children(helper.pid)
        finally:
            _kill_group(helper)


async def test_state_post_keeps_event_loop_serving(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-RECORD-16: saving terminal folders never pauses the event loop."""
    assert jupyter_data_dir() == str(jp_data_dir)

    def slow_cwd(pid):
        time.sleep(0.5)
        return str(tmp_path)

    def slow_workspace_names(workspaces_dir):
        time.sleep(0.5)
        return set()

    monkeypatch.setattr(routes, "_get_process_cwd", slow_cwd)
    monkeypatch.setattr(routes, "_workspace_terminal_names", slow_workspace_names)
    _inject_terminal(monkeypatch, jp_serverapp, os.getpid())

    gaps = []
    stop = asyncio.Event()

    async def ticker():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0.05)
    response = await jp_fetch(
        "jupyterlab-restore-terminals-fix", "state",
        method="POST", body=json.dumps({"names": ["t1"]})
    )
    stop.set()
    await task

    assert json.loads(response.body) == {"saved": {"t1": str(tmp_path)}}
    assert max(gaps) < 0.2


@linux_only
async def test_acc_reopen_5_other_workspace_terminal_kept(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-REOPEN-5, DEF-SERVER-2: a terminal in another workspace's layout keeps its folder."""
    assert jupyter_data_dir() == str(jp_data_dir)
    folder_a, folder_b, workspaces = tmp_path / "a", tmp_path / "b", tmp_path / "ws"
    for folder in (folder_a, folder_b, workspaces):
        folder.mkdir()
    _write_workspace(workspaces, "other", ["t2"])
    _use_workspaces_dir(monkeypatch, jp_serverapp, workspaces)
    one, two = _sleeper(folder_a), _sleeper(folder_b)
    try:
        manager = _inject_manager(
            monkeypatch, jp_serverapp, {"t1": one.pid, "t2": two.pid}
        )

        saved = await _post_state(jp_fetch, ["t1"])

        expected = {
            "t1": os.path.realpath(folder_a),
            "t2": os.path.realpath(folder_b),
        }
        assert saved == expected
        server_root = jp_serverapp.web_app.settings["server_root_dir"]
        assert routes._load_state(server_root) == expected
        # The frontend posts [] when its page has no terminal tab
        assert await _post_state(jp_fetch, []) == {"t2": expected["t2"]}
        # Restart: nothing runs, so prepopulate re-creates t2 in its folder
        manager.terminals.clear()
        # ACC-REOPEN-5: the workspace file still holds t2 while it is not
        # running, so the next save must keep its folder
        assert await _post_state(jp_fetch, []) == {"t2": expected["t2"]}
        routes.prepopulate_terminals(jp_serverapp)
        assert manager.created == [{"name": "t2", "cwd": expected["t2"]}]
    finally:
        _kill_group(one)
        _kill_group(two)


def test_workspace_terminal_names_reads_workspace_files_only(tmp_path):
    """DEF-SERVER-2: terminal names come from *.jupyterlab-workspace files directly in the folder."""
    _write_workspace(tmp_path, "a", ["1", "2"])
    _write_workspace(tmp_path, "b", ["2", "3"])
    (tmp_path / "sub").mkdir()
    _write_workspace(tmp_path / "sub", "nested", ["4"])
    (tmp_path / "folder.jupyterlab-workspace").mkdir()
    _write_workspace(tmp_path, "backup", ["5"])
    (tmp_path / "backup.jupyterlab-workspace").rename(
        tmp_path / "backup.jupyterlab-workspace.bak"
    )
    (tmp_path / "invalid.jupyterlab-workspace").write_text("{not json")
    (tmp_path / "nodata.jupyterlab-workspace").write_text('{"metadata": {}}')
    (tmp_path / "list.jupyterlab-workspace").write_text("[]")
    _write_workspace(tmp_path, "locked", ["6"])
    (tmp_path / "locked.jupyterlab-workspace").chmod(0)

    # Root reads a mode-000 file, so only an ordinary user sees it skipped
    expected = {"1", "2", "3"} | ({"6"} if os.geteuid() == 0 else set())
    assert routes._workspace_terminal_names(str(tmp_path)) == expected
    assert routes._workspace_terminal_names(str(tmp_path / "missing")) == set()
    assert routes._workspace_terminal_names(None) == set()


def test_macos_fallback_uses_pgrep_and_lsof(monkeypatch):
    """ACC-RECORD-13/17 (macOS): the pgrep walk and the lsof cwd read are wired."""
    calls = []

    def fake_run(args, *a, **kw):
        calls.append(args)
        if args[0] == "pgrep":
            return subprocess.CompletedProcess(args, 0, "4321\n", "")
        if args[0] == "lsof":
            return subprocess.CompletedProcess(
                args, 0, "p4321\nfcwd\nn/tmp/folder\n", ""
            )
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(routes.sys, "platform", "darwin")
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    assert routes._get_direct_children(1234) == [4321]
    assert routes._get_cwd_macos(4321) == "/tmp/folder"
    assert routes._try_get_cwd(4321) == "/tmp/folder"
    assert ["pgrep", "-P", "1234"] in calls
    assert ["lsof", "-a", "-p", "4321", "-d", "cwd", "-Fn"] in calls


def test_workspaces_dir_defaults_without_lab_app(jp_serverapp, jp_config_dir):
    """DEF-SERVER-2: without a loaded LabApp the handler reads JupyterLab's default folder."""
    settings = jp_serverapp.web_app.settings
    expected = os.path.join(str(jp_config_dir), "lab", "workspaces")
    assert settings["restore_terminals_fix_workspaces_dir"] == expected


def test_workspaces_dir_from_lab_app(
    jp_configurable_serverapp, jp_server_config, tmp_path
):
    """DEF-SERVER-2: the handler reads the workspaces folder of the loaded LabApp."""
    workspaces = str(tmp_path / "configured-workspaces")
    jp_server_config["ServerApp"]["jpserver_extensions"]["jupyterlab"] = True
    jp_server_config["LabApp"] = {"workspaces_dir": workspaces}

    app = jp_configurable_serverapp(config=jp_server_config)

    assert app.web_app.settings["restore_terminals_fix_workspaces_dir"] == workspaces


def test_acc_reopen_1_prepopulate_creates_saved_terminals(
    jp_environ, jp_data_dir, tmp_path
):
    """ACC-REOPEN-1 (unit): each saved terminal is re-created by name in its saved folder."""
    assert jupyter_data_dir() == str(jp_data_dir)
    sub1, sub2 = tmp_path / "sub1", tmp_path / "sub2"
    sub1.mkdir()
    sub2.mkdir()
    routes._save_state(str(tmp_path), {"1": str(sub1), "2": str(sub2)})
    manager = _fake_manager({})

    routes.prepopulate_terminals(_fake_server(manager, tmp_path))

    assert manager.created == [
        {"name": "1", "cwd": str(sub1)},
        {"name": "2", "cwd": str(sub2)},
    ]


@linux_only
async def test_acc_reopen_1_terminal_reopens_in_saved_folder(
    jp_fetch, jp_serverapp, jp_root_dir, jp_data_dir, no_startup_prepopulate
):
    """ACC-REOPEN-1 (integration): a real terminal is re-created in its saved subfolder."""
    assert jupyter_data_dir() == str(jp_data_dir)
    sub = jp_root_dir / "sub"
    sub.mkdir()
    manager = jp_serverapp.web_app.settings["terminal_manager"]
    try:
        await _create_terminal(jp_fetch, "1", sub)
        assert await _post_state(jp_fetch, ["1"]) == {"1": os.path.realpath(sub)}
        await _delete_terminal(jp_fetch, manager, "1")

        routes.prepopulate_terminals(jp_serverapp)

        assert list(manager.terminals) == ["1"]
        response = await jp_fetch("jupyterlab-restore-terminals-fix", "cwd", "1")
        assert json.loads(response.body) == {
            "terminal_name": "1",
            "cwd": os.path.realpath(sub),
            "relative_cwd": "sub",
        }
    finally:
        await _terminate_all(manager)


@pytest.fixture
def seeded_state(jp_environ, jp_root_dir):
    # Written before the server starts, as a previous server run would leave it
    folder = jp_root_dir / "seeded"
    folder.mkdir()
    routes._save_state(str(jp_root_dir), {"seed": str(folder)})
    return folder


@linux_only
async def test_acc_reopen_1_startup_recreates_saved_terminal(
    seeded_state, jp_fetch, jp_serverapp
):
    """ACC-REOPEN-1 (startup): loading the extension re-creates saved terminals."""
    manager = jp_serverapp.web_app.settings["terminal_manager"]
    try:
        await _await_until(lambda: "seed" in manager.terminals)
        response = await jp_fetch("jupyterlab-restore-terminals-fix", "cwd", "seed")
        assert json.loads(response.body)["cwd"] == os.path.realpath(seeded_state)
    finally:
        await _terminate_all(manager)


@linux_only
async def test_acc_reopen_2_no_cd_typed(
    jp_fetch, jp_serverapp, jp_root_dir, jp_data_dir, no_startup_prepopulate
):
    """ACC-REOPEN-2: the re-created terminal's output shows no line starting with cd."""
    assert jupyter_data_dir() == str(jp_data_dir)
    sub = jp_root_dir / "sub"
    sub.mkdir()
    manager = jp_serverapp.web_app.settings["terminal_manager"]
    try:
        await _create_terminal(jp_fetch, "1", sub)
        await _post_state(jp_fetch, ["1"])
        await _delete_terminal(jp_fetch, manager, "1")
        routes.prepopulate_terminals(jp_serverapp)
        terminal = manager.terminals["1"]

        def lines():
            return "".join(terminal.read_buffer).replace("\r", "").split("\n")

        await _await_until(lambda: terminal.read_buffer)
        terminal.ptyproc.write("pwd\n")
        folder = os.path.realpath(sub)
        await _await_until(lambda: any(line.endswith(folder) for line in lines()))

        assert [line for line in lines() if re.match(r"(\S*[$#] )?cd\b", line)] == []
    finally:
        await _terminate_all(manager)


@linux_only
async def test_acc_reopen_3_closed_tab_not_recreated(
    jp_fetch, jp_serverapp, jp_root_dir, jp_data_dir, no_startup_prepopulate
):
    """ACC-REOPEN-3: of two terminals, only the one still reported is saved and re-created."""
    assert jupyter_data_dir() == str(jp_data_dir)
    sub1, sub2 = jp_root_dir / "sub1", jp_root_dir / "sub2"
    sub1.mkdir()
    sub2.mkdir()
    manager = jp_serverapp.web_app.settings["terminal_manager"]
    server_root = jp_serverapp.web_app.settings["server_root_dir"]
    try:
        await _create_terminal(jp_fetch, "1", sub1)
        await _create_terminal(jp_fetch, "2", sub2)

        saved = await _post_state(jp_fetch, ["1"])

        assert saved == {"1": os.path.realpath(sub1)}
        assert routes._load_state(server_root) == saved
        await _delete_terminal(jp_fetch, manager, "1")
        await _delete_terminal(jp_fetch, manager, "2")
        routes.prepopulate_terminals(jp_serverapp)
        assert list(manager.terminals) == ["1"]
    finally:
        await _terminate_all(manager)


async def test_acc_reopen_4_last_tab_closed_recreates_nothing(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-REOPEN-4: posting no names, with no workspace file, empties the state."""
    assert jupyter_data_dir() == str(jp_data_dir)
    workspaces = tmp_path / "ws"
    workspaces.mkdir()
    _use_workspaces_dir(monkeypatch, jp_serverapp, workspaces)
    server_root = jp_serverapp.web_app.settings["server_root_dir"]
    routes._save_state(server_root, {"t1": str(tmp_path)})
    manager = _inject_terminal(monkeypatch, jp_serverapp, os.getpid())

    assert await _post_state(jp_fetch, []) == {}

    assert routes._load_state(server_root) == {}
    # Restart: nothing runs and nothing is saved, so nothing is re-created
    manager.terminals.clear()
    routes.prepopulate_terminals(jp_serverapp)
    assert manager.created == []


def test_acc_reopen_6_deleted_folder_not_recreated(
    jp_environ, jp_data_dir, tmp_path
):
    """ACC-REOPEN-6: a saved folder that no longer exists is skipped; startup continues."""
    assert jupyter_data_dir() == str(jp_data_dir)
    kept = tmp_path / "kept"
    kept.mkdir()
    routes._save_state(
        str(tmp_path), {"1": str(tmp_path / "deleted"), "2": str(kept)}
    )
    manager = _fake_manager({})

    routes.prepopulate_terminals(_fake_server(manager, tmp_path))

    assert manager.created == [{"name": "2", "cwd": str(kept)}]


def test_acc_reopen_7_running_name_not_replaced(
    jp_environ, jp_data_dir, tmp_path
):
    """ACC-REOPEN-7: startup never re-creates a saved name that is already running."""
    assert jupyter_data_dir() == str(jp_data_dir)
    routes._save_state(str(tmp_path), {"1": str(tmp_path)})
    manager = _fake_manager({"1": os.getpid()})

    routes.prepopulate_terminals(_fake_server(manager, tmp_path))

    assert manager.created == []


def test_acc_reopen_8_separate_state_per_root(jp_environ, jp_data_dir, tmp_path):
    """ACC-REOPEN-8: servers with different root folders keep separate state files."""
    assert jupyter_data_dir() == str(jp_data_dir)
    root_a, root_b = str(tmp_path / "a"), str(tmp_path / "b")

    path_a, path_b = routes._state_file(root_a), routes._state_file(root_b)

    assert path_a != path_b
    assert os.path.dirname(path_a) == os.path.join(
        str(jp_data_dir), "restore_terminals_fix"
    )
    routes._save_state(root_a, {"1": str(tmp_path)})
    assert routes._load_state(root_b) == {}


@linux_only
async def test_acc_record_11_cd_saved(
    jp_fetch, jp_serverapp, jp_root_dir, jp_data_dir, no_startup_prepopulate
):
    """ACC-RECORD-11: a cd typed in a real terminal is saved by the next POST /state."""
    assert jupyter_data_dir() == str(jp_data_dir)
    sub1, sub2 = jp_root_dir / "sub1", jp_root_dir / "sub2"
    sub1.mkdir()
    sub2.mkdir()
    manager = jp_serverapp.web_app.settings["terminal_manager"]
    server_root = jp_serverapp.web_app.settings["server_root_dir"]
    try:
        await _create_terminal(jp_fetch, "1", sub1)
        assert await _post_state(jp_fetch, ["1"]) == {"1": os.path.realpath(sub1)}

        manager.terminals["1"].ptyproc.write(f"cd {sub2}\n")

        target = os.path.realpath(sub2)
        deadline = time.monotonic() + 10
        while (await _post_state(jp_fetch, ["1"])).get("1") != target:
            assert time.monotonic() < deadline, "the cd never reached the state"
            await asyncio.sleep(0.1)
        assert routes._load_state(server_root) == {"1": target}
    finally:
        await _terminate_all(manager)


@linux_only
async def test_acc_record_12_closed_tab_dropped(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-RECORD-12: a terminal neither posted nor in any workspace layout leaves the state."""
    assert jupyter_data_dir() == str(jp_data_dir)
    workspaces = tmp_path / "ws"
    workspaces.mkdir()
    _write_workspace(workspaces, "other", ["t3"])
    _use_workspaces_dir(monkeypatch, jp_serverapp, workspaces)
    server_root = jp_serverapp.web_app.settings["server_root_dir"]
    helper = _sleeper(tmp_path)
    try:
        _inject_manager(
            monkeypatch, jp_serverapp, {"t1": helper.pid, "t2": helper.pid}
        )
        folder = os.path.realpath(tmp_path)
        assert await _post_state(jp_fetch, ["t1", "t2"]) == {
            "t1": folder,
            "t2": folder,
        }

        assert await _post_state(jp_fetch, ["t1"]) == {"t1": folder}

        assert routes._load_state(server_root) == {"t1": folder}
    finally:
        _kill_group(helper)


@linux_only
def test_acc_record_13_deepest_process_folder(tmp_path):
    """ACC-RECORD-13: the folder of the deepest process in the tree is returned."""
    folder_a, folder_b = tmp_path / "a", tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()
    deepest = os.path.realpath(folder_b)
    helper = subprocess.Popen(
        ["sh", "-c", 'cd "$1" && sleep 60 & wait', "sh", str(folder_b)],
        cwd=folder_a,
        start_new_session=True,
    )
    try:
        _wait_until(lambda: any(
            routes._get_cwd_linux(child) == deepest
            for child in _read_children(helper.pid, helper.pid)
        ))
        assert routes._get_cwd_linux(helper.pid) == os.path.realpath(folder_a)

        assert routes._get_process_cwd(helper.pid) == deepest
    finally:
        _kill_group(helper)


@linux_only
def test_acc_record_13_shell_preferred_at_equal_depth(tmp_path):
    """ACC-RECORD-13: at equal depth the shell's folder wins over another process."""
    folder_sleep, folder_shell = tmp_path / "sleep", tmp_path / "shell"
    folder_sleep.mkdir()
    folder_shell.mkdir()
    helper = subprocess.Popen(
        [sys.executable, "-c", SIBLINGS_HELPER, str(folder_sleep), str(folder_shell)],
        start_new_session=True,
    )
    try:
        def comms():
            children = routes._get_direct_children(helper.pid)
            return [routes._get_process_comm(child) for child in children]

        _wait_until(lambda: comms() == ["sleep", "sh"])

        # The sleep is listed first, so only the shell preference picks the shell
        assert routes._get_process_cwd(helper.pid) == os.path.realpath(folder_shell)
    finally:
        _kill_group(helper)


@linux_only
async def test_acc_record_15_exited_process_skipped(
    jp_fetch, jp_serverapp, jp_data_dir, monkeypatch, tmp_path
):
    """ACC-RECORD-15: a terminal whose process has exited is skipped; the save succeeds."""
    assert jupyter_data_dir() == str(jp_data_dir)
    helper = _sleeper(tmp_path)
    gone = subprocess.Popen(["true"])
    gone.wait()
    try:
        # Every /proc read of the exited process raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            os.listdir(f"/proc/{gone.pid}/task")
        # ACC-RECORD-15: force one /proc cwd read to fail during the POST
        gone_cwd = f"/proc/{gone.pid}/cwd"
        real_exists, real_readlink = os.path.exists, os.readlink

        def exists(path):
            return (
                path in (gone_cwd, f"/proc/{gone.pid}/environ")
                or real_exists(path)
            )

        def readlink(path):
            if path == gone_cwd:
                raise FileNotFoundError(path)
            return real_readlink(path)

        monkeypatch.setattr(routes.os.path, "exists", exists)
        monkeypatch.setattr(routes.os, "readlink", readlink)
        _inject_manager(
            monkeypatch, jp_serverapp, {"gone": gone.pid, "t1": helper.pid}
        )

        saved = await _post_state(jp_fetch, ["gone", "t1"])

        assert saved == {"t1": os.path.realpath(tmp_path)}
    finally:
        _kill_group(helper)


async def test_acc_record_18_no_terminal_service(jp_fetch, jp_serverapp, monkeypatch):
    """ACC-RECORD-18: POST /state answers 503 when the server has no terminal service."""
    monkeypatch.delitem(jp_serverapp.web_app.settings, "terminal_manager")

    response = await jp_fetch(
        "jupyterlab-restore-terminals-fix", "state",
        method="POST", body=json.dumps({"names": []}), raise_error=False
    )

    assert response.code == 503
