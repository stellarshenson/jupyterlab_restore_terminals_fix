import json
import os
import subprocess
import sys

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
import tornado


KNOWN_SHELLS = {'bash', 'zsh', 'fish', 'sh', 'dash', 'ksh', 'tcsh', 'csh'}


def _get_process_comm(pid: int) -> str | None:
    try:
        if sys.platform == "linux":
            comm_file = f"/proc/{pid}/comm"
            if os.path.exists(comm_file):
                with open(comm_file, "r") as f:
                    return f.read().strip()
        else:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return None


def _get_direct_children(parent_pid: int) -> list[int]:
    children = []
    try:
        if sys.platform == "linux":
            children_file = f"/proc/{parent_pid}/task/{parent_pid}/children"
            if os.path.exists(children_file):
                with open(children_file, "r") as f:
                    for child in f.read().strip().split():
                        try:
                            children.append(int(child))
                        except ValueError:
                            pass

        if not children:
            result = subprocess.run(
                ["pgrep", "-P", str(parent_pid)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                for pid_str in result.stdout.strip().split("\n"):
                    try:
                        children.append(int(pid_str))
                    except ValueError:
                        pass
    except Exception:
        pass
    return children


def _collect_process_tree(pid: int, depth: int, results: list) -> None:
    comm = _get_process_comm(pid)
    is_shell = comm in KNOWN_SHELLS if comm else False
    results.append((pid, depth, is_shell, comm))

    for child_pid in _get_direct_children(pid):
        _collect_process_tree(child_pid, depth + 1, results)


def _is_valid_cwd(path: str) -> bool:
    if not path or not path.startswith('/'):
        return False
    if path.startswith(('/proc/', '/sys/', '/dev/')):
        return False
    return os.path.isdir(path)


def _get_cwd_linux(pid: int) -> str | None:
    try:
        cwd_link = f"/proc/{pid}/cwd"
        if os.path.exists(cwd_link):
            return os.readlink(cwd_link)
    except (OSError, PermissionError):
        pass
    return None


def _get_pwd_from_environ(pid: int) -> str | None:
    try:
        environ_file = f"/proc/{pid}/environ"
        if os.path.exists(environ_file):
            with open(environ_file, "rb") as f:
                environ_data = f.read()
                for entry in environ_data.split(b"\x00"):
                    if entry.startswith(b"PWD="):
                        return entry[4:].decode("utf-8", errors="replace")
    except (OSError, PermissionError):
        pass
    return None


def _get_cwd_macos(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("n"):
                    return line[1:]
    except Exception:
        pass
    return None


def _try_get_cwd(pid: int) -> str | None:
    if sys.platform == "linux":
        cwd = _get_cwd_linux(pid)
        if cwd is None:
            cwd = _get_pwd_from_environ(pid)
        return cwd
    elif sys.platform == "darwin":
        return _get_cwd_macos(pid)
    else:
        cwd = _get_cwd_linux(pid)
        if cwd is None:
            cwd = _get_pwd_from_environ(pid)
        return cwd


def _get_process_cwd(pid: int) -> str | None:
    all_processes = []
    _collect_process_tree(pid, 0, all_processes)
    all_processes.sort(key=lambda x: (-x[1], not x[2]))

    for target_pid, depth, is_shell, comm in all_processes:
        cwd = _try_get_cwd(target_pid)
        if cwd and _is_valid_cwd(cwd):
            return cwd

    return _try_get_cwd(pid)


def _to_relative_cwd(cwd: str, server_root: str | None) -> str | None:
    """Express cwd relative to the server root.

    The built-in terminal:create-new command runs the stored cwd through
    contents.localPath() which strips the leading slash of an absolute
    path, so an absolute cwd ends up double-prefixed with the server root
    and the terminal silently opens at root. A path already relative to
    the server root survives that round-trip. Returns None when cwd is
    the root itself (nothing to restore) or lives outside the root
    (cannot be expressed relative to it).
    """
    if not server_root:
        return None
    root = os.path.realpath(os.path.expanduser(server_root))
    target = os.path.realpath(cwd)
    if target == root:
        return None
    rel = os.path.relpath(target, root)
    if rel.startswith(".."):
        return None
    return rel


def _get_terminal_cwd(
    terminal_manager, terminal_name: str, server_root: str | None = None
) -> dict:
    # Check if terminal exists without auto-creating it
    if terminal_name not in terminal_manager.terminals:
        return {"terminal_name": terminal_name, "error": "not found"}

    terminal = terminal_manager.terminals[terminal_name]
    ptyproc = getattr(terminal, "ptyproc", None)
    if ptyproc is None:
        return {"terminal_name": terminal_name, "error": "no process"}

    cwd = _get_process_cwd(ptyproc.pid)
    if cwd is None:
        return {"terminal_name": terminal_name, "error": "cwd unavailable"}

    result = {"terminal_name": terminal_name, "cwd": cwd}
    relative = _to_relative_cwd(cwd, server_root)
    if relative is not None:
        result["relative_cwd"] = relative
    return result


class TerminalCwdHandler(APIHandler):
    @tornado.web.authenticated
    async def get(self, terminal_name: str):
        terminal_manager = self.settings.get("terminal_manager")
        if terminal_manager is None:
            self.set_status(503)
            self.finish(json.dumps({"error": "Terminal service not available"}))
            return

        server_root = self.settings.get("server_root_dir")
        result = _get_terminal_cwd(terminal_manager, terminal_name, server_root)
        if "error" in result:
            self.set_status(404 if result["error"] == "not found" else 500)
        self.finish(json.dumps(result))


class AllTerminalCwdsHandler(APIHandler):
    @tornado.web.authenticated
    async def get(self):
        terminal_manager = self.settings.get("terminal_manager")
        if terminal_manager is None:
            self.set_status(503)
            self.finish(json.dumps({"error": "Terminal service not available"}))
            return

        server_root = self.settings.get("server_root_dir")
        terminals = []
        for name in list(terminal_manager.terminals.keys()):
            result = _get_terminal_cwd(terminal_manager, name, server_root)
            if "cwd" in result:
                terminals.append(result)

        self.finish(json.dumps({"terminals": terminals}))


def setup_route_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    cwd_pattern = url_path_join(
        base_url, "jupyterlab-restore-terminals-fix", "cwd", "([^/]+)"
    )
    cwds_pattern = url_path_join(
        base_url, "jupyterlab-restore-terminals-fix", "cwds"
    )

    handlers = [
        (cwd_pattern, TerminalCwdHandler),
        (cwds_pattern, AllTerminalCwdsHandler),
    ]
    web_app.add_handlers(host_pattern, handlers)
