"""Background daemon that monitors iLink messages and writes to inbox."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from .client import Client as _BaseClient
from .filelock import locked_append_line, locked_read_json, locked_write_json, locked_write_text
from .helpers import extract_text
from .monitor import MonitorOptions, monitor

logger = logging.getLogger("openilink.daemon")

ILINK_DIR = Path.home() / ".ilink"
STATE_FILE = ILINK_DIR / "state.json"
INBOX_FILE = ILINK_DIR / "inbox.jsonl"
BUF_FILE = ILINK_DIR / "sync_buf.dat"
PID_FILE = ILINK_DIR / "daemon.pid"
LOG_FILE = ILINK_DIR / "daemon.log"
EXPIRED_FILE = ILINK_DIR / "expired"


def _ensure_dir():
    ILINK_DIR.mkdir(exist_ok=True)


def _setup_logging():
    """Configure daemon logging to both stderr and daemon.log."""
    _ensure_dir()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(logging.INFO)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)


def load_state() -> dict:
    return locked_read_json(STATE_FILE, default={})


def save_state(state: dict):
    _ensure_dir()
    locked_write_json(STATE_FILE, state)


def _handle_session_expired():
    """Write expired marker and log warning when session expires."""
    logger.warning("session expired — token is no longer valid, re-login required")
    try:
        EXPIRED_FILE.write_text(str(time.time()))
    except OSError:
        pass


def run_daemon():
    """Run the message monitor daemon (foreground, called by subprocess)."""
    _ensure_dir()
    _setup_logging()

    state = load_state()
    token = state.get("token", "")
    base_url = state.get("base_url", "")

    if not token:
        logger.error("No token found. Run login first.")
        sys.exit(1)

    # Import here to get the full Client with monitor
    from . import Client
    client = Client(token=token)
    if base_url:
        client.base_url = base_url

    # Write PID (under file lock to avoid races with CLI readers)
    locked_write_text(PID_FILE, str(os.getpid()))

    # Handle stop signal
    def on_signal(sig, frame):
        client.stop()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, on_signal)

    # Load sync cursor
    buf = ""
    from .filelock import locked_read_text
    buf_text = locked_read_text(BUF_FILE)
    if buf_text:
        buf = buf_text.strip()

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
        locked_append_line(INBOX_FILE, json.dumps(entry, ensure_ascii=False))

    logger.info("ilink daemon started (pid=%d)", os.getpid())

    monitor(client, handler, MonitorOptions(
        initial_buf=buf,
        on_buf_update=lambda b: locked_write_text(BUF_FILE, b),
        on_error=lambda e: logger.error("%s", e),
        on_session_expired=lambda: _handle_session_expired(),
    ))

    # Cleanup PID
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    logger.info("ilink daemon stopped")
