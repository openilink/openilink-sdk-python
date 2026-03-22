"""Background daemon that monitors iLink messages and writes to inbox."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

from .client import Client as _BaseClient
from .helpers import extract_text
from .monitor import MonitorOptions, monitor


ILINK_DIR = Path(".ilink")
STATE_FILE = ILINK_DIR / "state.json"
INBOX_FILE = ILINK_DIR / "inbox.jsonl"
BUF_FILE = ILINK_DIR / "sync_buf.dat"
PID_FILE = ILINK_DIR / "daemon.pid"


def _ensure_dir():
    ILINK_DIR.mkdir(exist_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    _ensure_dir()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def run_daemon():
    """Run the message monitor daemon (foreground, called by subprocess)."""
    _ensure_dir()

    state = load_state()
    token = state.get("token", "")
    base_url = state.get("base_url", "")

    if not token:
        print("ERROR: No token found. Run login first.", file=sys.stderr)
        sys.exit(1)

    # Import here to get the full Client with monitor
    from . import Client
    client = Client(token=token)
    if base_url:
        client.base_url = base_url

    # Write PID
    PID_FILE.write_text(str(os.getpid()))

    # Handle stop signal
    def on_signal(sig, frame):
        client.stop()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    # Load sync cursor
    buf = ""
    if BUF_FILE.exists():
        buf = BUF_FILE.read_text().strip()

    def handler(msg):
        text = extract_text(msg)
        entry = {
            "ts": time.time(),
            "from_user_id": msg.from_user_id,
            "to_user_id": msg.to_user_id,
            "message_id": msg.message_id,
            "text": text,
            "context_token": msg.context_token,
            "message_type": int(msg.message_type),
            "session_id": msg.session_id,
            "group_id": msg.group_id,
        }
        with open(INBOX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()

    print(f"ilink daemon started (pid={os.getpid()})", flush=True)

    monitor(client, handler, MonitorOptions(
        initial_buf=buf,
        on_buf_update=lambda b: BUF_FILE.write_text(b),
        on_error=lambda e: print(f"[daemon] {e}", file=sys.stderr, flush=True),
        on_session_expired=lambda: print("[daemon] session expired", file=sys.stderr, flush=True),
    ))

    # Cleanup PID
    if PID_FILE.exists():
        PID_FILE.unlink()
    print("ilink daemon stopped", flush=True)
