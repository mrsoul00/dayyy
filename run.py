#!/usr/bin/env python3
# Made for IamGunpoint
"""
IamGunpoint's Daytona SSH Terminal
Simple terminal-based Daytona sandbox manager.

Install:
  pip install daytona

Run:
  python3 app.py

First run:
  - checks ~/.daytona_ssh/config.json
  - if no API key, asks for it
  - saves it

Menu:
  1) create
  2) stop
  3) start
  4) delete
  5) terminal
  6) exit
  plus extra useful options.

Notes:
  - Daytona sandboxes have auto-timeout, no need to set manually
  - This is SSH-like, not real OpenSSH. It runs shell commands through Daytona SDK.
  - Commands that require a true interactive TTY, like `sudo su`, may not work
"""

from __future__ import annotations

import getpass
import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from daytona import Daytona
    from daytona.exceptions import DaytonaError
except Exception:
    Daytona = None
    DaytonaError = Exception

APP_DIR = Path.home() / ".daytona_ssh"
CONFIG_FILE = APP_DIR / "config.json"
DEFAULT_CWD = "/workspace"
OWNER_NAME = "IamGunpoint"


# ---------- tiny colors ----------
class C:
    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    red = "\033[91m"
    green = "\033[92m"
    yellow = "\033[93m"
    blue = "\033[94m"
    magenta = "\033[95m"
    cyan = "\033[96m"


def color(text: str, c: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    return c + text + C.reset


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause() -> None:
    input(color("\npress enter...", C.dim))


def banner() -> None:
    clear()
    art = f"""
{C.cyan}{C.bold}╔══════════════════════════════════════════════════════════════╗
║            D A Y T O N A   S S H   T E R M I N A L         ║
║                       by {OWNER_NAME:<34}║
╚══════════════════════════════════════════════════════════════╝{C.reset}
""".rstrip()
    print(art)
    print(color("simple · fast · sandbox terminal · free\n", C.dim))


def ok(msg: str) -> None:
    print(color("✓ ", C.green) + msg)


def warn(msg: str) -> None:
    print(color("! ", C.yellow) + msg)


def bad(msg: str) -> None:
    print(color("✗ ", C.red) + msg)


def info(msg: str) -> None:
    print(color("› ", C.cyan) + msg)


# ---------- config ----------
def load_config() -> Dict[str, Any]:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass


def require_sdk() -> None:
    if Daytona is not None:
        return
    bad("daytona SDK is not installed")
    print("\nInstall it:")
    print(color("  pip install daytona", C.cyan))
    sys.exit(2)


def setup_api_key() -> Tuple[str, Optional[str]]:
    """Returns (api_key, server_url)"""
    cfg = load_config()
    
    # Check if we have both
    if cfg.get("api_key") and cfg.get("server_url"):
        return str(cfg["api_key"]), str(cfg.get("server_url", ""))
    
    # Check env vars
    if os.environ.get("DAYTONA_API_KEY") and os.environ.get("DAYTONA_SERVER_URL"):
        cfg["api_key"] = os.environ["DAYTONA_API_KEY"]
        cfg["server_url"] = os.environ["DAYTONA_SERVER_URL"]
        save_config(cfg)
        return cfg["api_key"], cfg["server_url"]
    
    banner()
    warn("No API key found in ~/.daytona_ssh/config.json")
    print("Paste your Daytona API key and server URL.")
    print("It will be saved locally.")
    print(color("Tip: you can also set DAYTONA_API_KEY and DAYTONA_SERVER_URL env vars.\n", C.dim))
    
    server_url = input("Daytona Server URL (e.g., https://app.daytona.io): ").strip()
    if not server_url:
        server_url = "https://app.daytona.io"
    
    key = getpass.getpass("Daytona API key: ").strip()
    if not key:
        bad("API key required")
        sys.exit(1)
    
    cfg["api_key"] = key
    cfg["server_url"] = server_url
    save_config(cfg)
    ok("Configuration saved")
    time.sleep(0.7)
    return key, server_url


def get_daytona_client() -> Daytona:
    require_sdk()
    api_key, server_url = setup_api_key()
    return Daytona(api_key=api_key, server_url=server_url)


def set_current(sandbox_id: str) -> None:
    cfg = load_config()
    cfg["current_sandbox"] = sandbox_id
    cfg.setdefault("cwd", {})[sandbox_id] = cfg.setdefault("cwd", {}).get(sandbox_id, DEFAULT_CWD)
    save_config(cfg)


def get_current() -> str:
    return str(load_config().get("current_sandbox", ""))


def get_cwd(sandbox_id: str) -> str:
    return str(load_config().get("cwd", {}).get(sandbox_id, DEFAULT_CWD))


def set_cwd(sandbox_id: str, cwd: str) -> None:
    cfg = load_config()
    cfg.setdefault("cwd", {})[sandbox_id] = cwd
    save_config(cfg)


def reset_config() -> None:
    cfg = load_config()
    cfg.pop("api_key", None)
    cfg.pop("server_url", None)
    save_config(cfg)
    warn("Configuration removed. Restart script to login again.")


# ---------- Daytona helpers ----------
def sid_of(sb: Any) -> str:
    return str(getattr(sb, "id", None) or getattr(sb, "sandbox_id", None) or "unknown")


def val(obj: Any, key: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def connect(client: Daytona, sandbox_id: Optional[str] = None) -> Any:
    sid = sandbox_id or get_current()
    if not sid:
        sid = input("Sandbox ID: ").strip()
    if not sid:
        raise RuntimeError("No sandbox selected")
    sb = client.get_sandbox(sid)
    set_current(sid_of(sb))
    return sb


def create(client: Daytona) -> Any:
    template = input(f"Template [python]: ").strip() or "python"
    
    info(f"creating sandbox template={template} ...")
    try:
        sb = client.create_sandbox(language=template)
        set_current(sid_of(sb))
        ok(f"created {sid_of(sb)}")
        show_info(sb)
        return sb
    except Exception as e:
        raise RuntimeError(f"Could not create sandbox: {e}")


def list_sandboxes(client: Daytona) -> list[Any]:
    info("fetching sandboxes...")
    boxes = client.list_sandboxes()
    if not boxes:
        warn("No sandboxes found")
        return []
    print()
    print(color("#   Sandbox ID                         Status       Template", C.bold))
    print(color("─" * 70, C.dim))
    for i, sb in enumerate(boxes, 1):
        try:
            info_data = sb.get_info() if hasattr(sb, 'get_info') else {}
        except Exception:
            info_data = {}
        sid = sid_of(sb)
        status = str(val(info_data, "state", val(info_data, "status", "?"))).ljust(12)
        template = str(val(info_data, "language", val(info_data, "template_name", "")))
        mark = "*" if sid == get_current() else " "
        print(f"{mark}{i:<3} {sid:<34} {status} {template}")
    print()
    return boxes


def choose_sandbox(client: Daytona) -> Optional[str]:
    boxes = list_sandboxes(client)
    if not boxes:
        return None
    choice = input("Choose # or paste sandbox id: ").strip()
    if not choice:
        return None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(boxes):
            sid = sid_of(boxes[idx])
            set_current(sid)
            ok(f"selected {sid}")
            return sid
    set_current(choice)
    ok(f"selected {choice}")
    return choice


def show_info(sb: Any) -> None:
    try:
        inf = sb.get_info() if hasattr(sb, 'get_info') else sb.__dict__
    except Exception as e:
        bad(f"could not get info: {e}")
        return
    print()
    print(color("Sandbox Info", C.bold + C.cyan))
    print(color("─" * 50, C.dim))
    for k in ["id", "sandbox_id", "state", "status", "language", "template_name", "region", "created_at", "expires_at"]:
        v = val(inf, k, None)
        if v:
            print(f"{k:14}: {v}")
    print()


def action(client: Daytona, name: str) -> None:
    sb = connect(client)
    sid = sid_of(sb)
    if name == "start":
        info(f"starting {sid}...")
        sb.start()
        ok("started")
    elif name == "stop":
        info(f"stopping {sid}...")
        sb.stop()
        ok("stopped")
    elif name == "delete":
        confirm = input(color(f"Delete {sid} permanently? type DELETE: ", C.red)).strip()
        if confirm != "DELETE":
            warn("cancelled")
            return
        sb.delete()
        ok("deleted")
        cfg = load_config()
        if cfg.get("current_sandbox") == sid:
            cfg.pop("current_sandbox", None)
        cfg.get("cwd", {}).pop(sid, None)
        save_config(cfg)
    elif name == "pause":
        try:
            sb.pause()
            ok("paused")
        except Exception:
            warn("pause not supported, stopping instead")
            sb.stop()
    elif name == "resume":
        try:
            sb.resume()
            ok("resumed")
        except Exception:
            warn("resume not supported, starting instead")
            sb.start()


# ---------- terminal ----------
def run_command(sb: Any, command: str, cwd: str, timeout: int = 300) -> Tuple[str, str, int, str]:
    """
    Run command in Daytona sandbox and preserve cwd.
    """
    marker = "__DAYTONA_SSH_CWD__"
    safe_cwd = shlex.quote(cwd)

    wrapped = (
        f"cd {safe_cwd} 2>/dev/null || cd /workspace 2>/dev/null || cd /\n"
        f"{command}\n"
        f"__daytona_ssh_code=$?\n"
        f"printf '\\n{marker}:%s\\n' \"$PWD\"\n"
        f"exit $__daytona_ssh_code\n"
    )

    res = sb.process.run(wrapped, timeout=timeout)
    stdout = str(getattr(res, "stdout", "") or "")
    stderr = str(getattr(res, "stderr", "") or "")
    code_raw = getattr(res, "exit_code", 0)
    code = int(code_raw if code_raw is not None else 0)
    new_cwd = cwd

    if marker + ":" in stdout:
        before, _, after = stdout.rpartition(marker + ":")
        stdout = before.rstrip("\n") + ("\n" if before.rstrip("\n") else "")
        new_cwd = after.splitlines()[0].strip() or cwd

    return stdout, stderr, code, new_cwd


def terminal_help() -> None:
    print(color("""
Terminal commands:
  help / :help              show this
  exit / :exit              exit terminal, keep sandbox running
  clear                     clear screen
  info                      sandbox info
  files [path]              list remote files
  cat <file>                read remote file
  upload <local> <remote>   upload text file
  download <remote> <local> download text file
  py                        paste Python code, end with EOF
  delete                    delete sandbox and exit

Anything else runs as shell command in the sandbox.
Examples:
  pwd
  ls -la
  cd /workspace
  pip install requests
  python --version

Note:
  sudo su may not become an interactive root shell because Daytona command execution
  is not a full PTY/OpenSSH session. Try direct commands like:
    whoami
    sudo whoami
    sudo apt update
""".strip(), C.cyan))


def paste_until_eof(language: str) -> str:
    print(f"Paste {language} code. End with a single line: EOF")
    lines = []
    while True:
        line = input()
        if line.strip() == "EOF":
            break
        lines.append(line)
    return "\n".join(lines)


def terminal(client: Daytona) -> None:
    sb = connect(client)
    sid = sid_of(sb)
    cwd = get_cwd(sid)
    clear()
    ok(f"connected terminal: {sid}")
    print(color("type help for terminal commands\n", C.dim))

    while True:
        try:
            cmd = input(color(f"{sid[:10]}:{cwd}$ ", C.cyan + C.bold))
        except (KeyboardInterrupt, EOFError):
            print()
            warn("terminal closed; sandbox still running")
            return

        raw = cmd
        cmd = cmd.strip()
        if not cmd:
            continue
        try:
            if cmd in {"exit", ":exit", "quit"}:
                warn("terminal closed; sandbox still running")
                return
            if cmd in {"help", ":help"}:
                terminal_help()
                continue
            if cmd == "clear":
                clear()
                continue
            if cmd == "info":
                show_info(sb)
                continue
            if cmd.startswith("files"):
                parts = shlex.split(cmd)
                path = parts[1] if len(parts) > 1 else cwd
                files = sb.fs.list_dir(path)
                for f in files:
                    name = val(f, "name", str(f))
                    is_dir = val(f, "is_dir", False)
                    size = val(f, "size", "?")
                    prefix = "📁" if is_dir else "📄"
                    print(f"{prefix} {name} ({size} bytes)")
                continue
            if cmd.startswith("cat "):
                path = shlex.split(cmd)[1]
                content = sb.fs.read_file(path)
                print(content)
                continue
            if cmd.startswith("upload "):
                _, local, remote = shlex.split(cmd)
                data = Path(local).read_text(errors="replace")
                sb.fs.write_file(remote, data)
                ok(f"uploaded {local} -> {remote}")
                continue
            if cmd.startswith("download "):
                _, remote, local = shlex.split(cmd)
                data = sb.fs.read_file(remote)
                Path(local).write_text(str(data))
                ok(f"downloaded {remote} -> {local}")
                continue
            if cmd == "py":
                code = paste_until_eof("Python")
                res = sb.process.run(f"python3 -c {shlex.quote(code)}", timeout=300)
                out = getattr(res, "stdout", "") or ""
                err = getattr(res, "stderr", "") or ""
                if out:
                    print(out.rstrip())
                if err:
                    print(color(err.rstrip(), C.red))
                continue
            if cmd == "delete":
                confirm = input(color("Delete sandbox permanently? type DELETE: ", C.red)).strip()
                if confirm == "DELETE":
                    sb.delete()
                    ok("deleted")
                    return
                warn("cancelled")
                continue

            start = time.time()
            stdout, stderr, code, cwd = run_command(sb, raw, cwd)
            set_cwd(sid, cwd)
            if stdout:
                print(stdout.rstrip("\n"))
            if stderr:
                print(color(stderr.rstrip("\n"), C.red), file=sys.stderr)
            took = time.time() - start
            if code == 0:
                print(color(f"exit 0 · {took:.2f}s", C.dim))
            else:
                print(color(f"exit {code} · {took:.2f}s", C.red))
        except Exception as e:
            bad(str(e))


# ---------- menu ----------
def menu(client: Daytona) -> None:
    while True:
        banner()
        current = get_current()
        print(color(f"Current sandbox: {current or 'none selected'}", C.bold))
        print()
        print("1) create")
        print("2) stop")
        print("3) start")
        print("4) delete")
        print("5) terminal")
        print("6) exit")
        print(color("\nMore:", C.dim))
        print("7) list/select sandboxes")
        print("8) info")
        print("9) change configuration")
        print()
        choice = input(color("Choose: ", C.cyan)).strip().lower()
        try:
            if choice == "1":
                create(client)
                pause()
            elif choice == "2":
                action(client, "stop")
                pause()
            elif choice == "3":
                action(client, "start")
                pause()
            elif choice == "4":
                action(client, "delete")
                pause()
            elif choice == "5":
                terminal(client)
                pause()
            elif choice == "6" or choice in {"exit", "q", "quit"}:
                ok(f"bye {OWNER_NAME}")
                return
            elif choice == "7":
                choose_sandbox(client)
                pause()
            elif choice == "8":
                show_info(connect(client))
                pause()
            elif choice == "9":
                reset_config()
                return
            else:
                warn("invalid choice")
                time.sleep(0.8)
        except DaytonaError as e:
            bad(f"Daytona error: {e}")
            pause()
        except Exception as e:
            bad(str(e))
            pause()


def main() -> None:
    require_sdk()
    client = get_daytona_client()
    menu(client)


if __name__ == "__main__":
    main()
