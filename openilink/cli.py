"""CLI entry point for the openilink SDK.

Usage:
    python -m openilink login       # QR login, save token
    python -m openilink start       # Start background daemon
    python -m openilink stop        # Stop daemon
    python -m openilink status      # Show daemon status
    python -m openilink send <user> <text>  # Send a message
    python -m openilink check       # Print new messages as JSON
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .daemon import (
    ILINK_DIR, STATE_FILE, INBOX_FILE, PID_FILE,
    _ensure_dir, load_state, save_state,
)


def cmd_login():
    """QR login and save token."""
    from . import Client, LoginCallbacks
    from .helpers import print_qrcode

    client = Client()
    print("Fetching QR code...")
    result = client.login_with_qr(
        callbacks=LoginCallbacks(
            on_qrcode=lambda url: (print("\nScan with WeChat:"), print_qrcode(url)),
            on_scanned=lambda: print("Scanned, confirm on WeChat..."),
            on_expired=lambda n, mx: print(f"QR expired, refreshing ({n}/{mx})..."),
        )
    )

    if not result.connected:
        print(f"Login failed: {result.message}", file=sys.stderr)
        sys.exit(1)

    save_state({
        "token": result.bot_token,
        "base_url": result.base_url,
        "bot_id": result.bot_id,
        "user_id": result.user_id,
    })
    print(f"\nLogin success! BotID={result.bot_id} UserID={result.user_id}")
    print(f"Token saved to {STATE_FILE}")


def cmd_start():
    """Start the background daemon."""
    _ensure_dir()
    state = load_state()
    if not state.get("token"):
        print("No token found. Run 'python -m openilink login' first.", file=sys.stderr)
        sys.exit(1)

    if _is_daemon_running():
        print(f"Daemon already running (pid={_read_pid()})")
        return

    # Start daemon as background subprocess
    daemon_cmd = [sys.executable, "-c", "from openilink.daemon import run_daemon; run_daemon()"]

    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        proc = subprocess.Popen(
            daemon_cmd,
            stdout=open(ILINK_DIR / "daemon.log", "a"),
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    else:
        proc = subprocess.Popen(
            daemon_cmd,
            stdout=open(ILINK_DIR / "daemon.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    # Wait a moment for PID file
    time.sleep(1)
    pid = proc.pid
    print(f"Daemon started (pid={pid})")
    print(f"Log: {ILINK_DIR / 'daemon.log'}")


def cmd_stop():
    """Stop the background daemon."""
    pid = _read_pid()
    if pid is None:
        print("No daemon running.")
        return

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
        else:
            os.kill(pid, 15)  # SIGTERM
        print(f"Daemon stopped (pid={pid})")
    except (OSError, ProcessLookupError):
        print(f"Daemon process {pid} not found, cleaning up.")

    if PID_FILE.exists():
        PID_FILE.unlink()


def cmd_status():
    """Show daemon status."""
    state = load_state()
    if not state:
        print("Not logged in. Run 'python -m openilink login'")
        return

    print(f"BotID:  {state.get('bot_id', 'N/A')}")
    print(f"UserID: {state.get('user_id', 'N/A')}")
    print(f"Token:  {state.get('token', '')[:20]}...")

    if _is_daemon_running():
        print(f"Daemon: running (pid={_read_pid()})")
    else:
        print("Daemon: stopped")

    if INBOX_FILE.exists():
        count = sum(1 for _ in open(INBOX_FILE, encoding="utf-8"))
        cursor = _read_cursor()
        unread = count - cursor
        print(f"Inbox:  {count} total, {unread} unread")
    else:
        print("Inbox:  empty")


def cmd_send(user_id: str, text: str):
    """Send a message to a user."""
    state = load_state()
    if not state.get("token"):
        print("Not logged in.", file=sys.stderr)
        sys.exit(1)

    from . import Client
    client = Client(token=state["token"])
    if state.get("base_url"):
        client.base_url = state["base_url"]

    # Try to load context token from inbox
    ctx_token = _find_context_token(user_id)
    if not ctx_token:
        print(f"No context token for {user_id}. User must send a message first.",
              file=sys.stderr)
        sys.exit(1)

    client_id = client.send_text(user_id, text, ctx_token)
    print(json.dumps({"ok": True, "client_id": client_id, "to": user_id}))


def cmd_check():
    """Print new (unread) messages as JSON lines."""
    if not INBOX_FILE.exists():
        print("[]")
        return

    cursor = _read_cursor()
    messages = []

    with open(INBOX_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < cursor:
                continue
            line = line.strip()
            if line:
                messages.append(json.loads(line))

    # Update cursor
    new_cursor = cursor + len(messages)
    _write_cursor(new_cursor)

    print(json.dumps(messages, ensure_ascii=False, indent=2))


# --- helpers ---

def _read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except ValueError:
            return None
    return None


def _is_daemon_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


CURSOR_FILE = ILINK_DIR / "cursor"


def _read_cursor() -> int:
    if CURSOR_FILE.exists():
        try:
            return int(CURSOR_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def _write_cursor(n: int):
    _ensure_dir()
    CURSOR_FILE.write_text(str(n))


def _find_context_token(user_id: str) -> str | None:
    """Find the latest context token for a user from inbox."""
    if not INBOX_FILE.exists():
        return None
    token = None
    with open(INBOX_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("from_user_id") == user_id and msg.get("context_token"):
                token = msg["context_token"]
    return token


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "login":
        cmd_login()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "send":
        if len(args) < 3:
            print("Usage: python -m openilink send <user_id> <text>", file=sys.stderr)
            sys.exit(1)
        cmd_send(args[1], " ".join(args[2:]))
    elif cmd == "check":
        cmd_check()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
