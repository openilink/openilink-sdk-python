"""MCP server for WeChat messaging via iLink.

Provides a Claude Code channel integration similar to the Telegram plugin.
WeChat messages appear in the Claude Code conversation via
notifications/claude/channel. Claude replies using the wechat_reply tool.

Requires:
    - iLink daemon running (auto-started if token exists)
    - Token saved via: python -m openilink login
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .filelock import (
    file_lock, locked_read_json, locked_read_lines,
    locked_read_text, locked_write_text,
)


# ── MCP Protocol (JSON-RPC 2.0 over stdio) ─────────────────────────

_write_lock = threading.Lock()


def _send(msg: dict):
    data = json.dumps(msg, ensure_ascii=False)
    with _write_lock:
        sys.stdout.write(data + "\n")
        sys.stdout.flush()


def _send_result(req_id, result: dict):
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _send_error(req_id, code: int, message: str):
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _notify(method: str, params: dict | None = None):
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    _send(msg)


def _log(level: str, data: str):
    _notify("notifications/message", {"level": level, "logger": "wechat", "data": data})


def _channel_message(content: str, meta: dict):
    """Push an incoming WeChat message into the Claude Code conversation."""
    _notify("notifications/claude/channel", {"content": content, "meta": meta})


# ── Paths & State ───────────────────────────────────────────────────

ILINK_DIR = Path(".ilink")
STATE_FILE = ILINK_DIR / "state.json"
INBOX_FILE = ILINK_DIR / "inbox.jsonl"
PID_FILE = ILINK_DIR / "daemon.pid"
CURSOR_FILE = ILINK_DIR / "mcp_cursor"
EXPIRED_FILE = ILINK_DIR / "expired"
MCP_PID_FILE = ILINK_DIR / "mcp.pid"

# Singleton: stop any existing MCP server before we start
_stop_event = threading.Event()

_ctx_tokens: dict[str, str] = {}

# Pending messages awaiting reply: {user_id: (timestamp, context_token, text)}
_pending: dict[str, tuple[float, str, str]] = {}
_pending_lock = threading.Lock()

# Track user_ids that have already been replied to (guards auto-ack race)
_replied: set[str] = set()

# Track pushed message IDs to prevent replays
_pushed_ids: set[str] = set()

# Auto-ack timeout: if Claude doesn't reply within this many seconds,
# the MCP server sends a fallback message directly.
AUTO_ACK_TIMEOUT = float(os.environ.get("WECHAT_AUTO_ACK_TIMEOUT", "30"))
AUTO_ACK_MESSAGE = os.environ.get("WECHAT_AUTO_ACK_MESSAGE", "消息已收到，正在处理中，请稍后...")


def _load_state() -> dict:
    return locked_read_json(STATE_FILE, default={})


def _read_cursor() -> int:
    try:
        text = locked_read_text(CURSOR_FILE)
        if text:
            return int(text.strip())
    except (FileNotFoundError, ValueError, OSError):
        pass
    return 0


def _write_cursor(n: int):
    try:
        ILINK_DIR.mkdir(exist_ok=True)
        locked_write_text(CURSOR_FILE, str(n))
    except OSError:
        pass  # best-effort; don't crash on write failure


# ── Singleton MCP ──────────────────────────────────────────────────

def _kill_old_mcp():
    """Stop any previously running MCP server so only one handles WeChat."""
    try:
        pid_text = MCP_PID_FILE.read_text().strip()
        old_pid = int(pid_text)
    except (FileNotFoundError, ValueError, OSError):
        return
    if old_pid == os.getpid():
        return
    try:
        if sys.platform == "win32":
            # Send CTRL_BREAK to the old process group
            os.kill(old_pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(old_pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass  # already dead


def _write_mcp_pid():
    """Write our PID so the next MCP server can stop us."""
    ILINK_DIR.mkdir(exist_ok=True)
    try:
        locked_write_text(MCP_PID_FILE, str(os.getpid()))
    except OSError:
        pass


def _cleanup_mcp_pid():
    try:
        MCP_PID_FILE.unlink()
    except OSError:
        pass


# ── Daemon ──────────────────────────────────────────────────────────

def _daemon_running() -> bool:
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return False
    try:
        if sys.platform == "win32":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def _ensure_daemon():
    if _daemon_running():
        return True
    state = _load_state()
    if not state.get("token"):
        return False
    ILINK_DIR.mkdir(exist_ok=True)
    cmd = [sys.executable, "-c", "from openilink.daemon import run_daemon; run_daemon()"]
    log_fh = open(ILINK_DIR / "daemon.log", "a")
    try:
        kw: dict = dict(
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kw["start_new_session"] = True
        subprocess.Popen(cmd, **kw)
    finally:
        log_fh.close()
    time.sleep(1.5)
    return _daemon_running()


# ── Message handling ────────────────────────────────────────────────

def _poll_new_messages() -> list[dict]:
    if not INBOX_FILE.exists():
        return []
    cursor = _read_cursor()
    msgs: list[dict] = []
    lines = locked_read_lines(INBOX_FILE)
    total = len(lines)
    for i, line in enumerate(lines):
        if i < cursor:
            continue
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            msgs.append(msg)
            uid = msg.get("from_user_id", "")
            ct = msg.get("context_token", "")
            if uid and ct:
                if len(_ctx_tokens) > 1000:
                    _ctx_tokens.clear()
                _ctx_tokens[uid] = ct
        except json.JSONDecodeError:
            pass
    _write_cursor(total)
    return msgs


def _do_reply(user_id: str, text: str) -> dict:
    # Mark as replied — cancel any pending auto-ack
    with _pending_lock:
        _pending.pop(user_id, None)
        if len(_replied) > 1000:
            _replied.clear()
        _replied.add(user_id)

    state = _load_state()
    if not state.get("token"):
        return _tool_error("Not logged in. Run: python -m openilink login")

    ctx = _ctx_tokens.get(user_id)
    if not ctx and INBOX_FILE.exists():
        for line in locked_read_lines(INBOX_FILE):
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
                if m.get("from_user_id") == user_id and m.get("context_token"):
                    ctx = m["context_token"]
            except json.JSONDecodeError:
                pass
    if not ctx:
        return _tool_error(f"No context token for {user_id}. User must message the bot first.")

    from openilink import Client
    client = Client(token=state["token"])
    if state.get("base_url"):
        client.base_url = state["base_url"]
    try:
        client.send_text(user_id, text, ctx)
        return _tool_ok(f"Sent to {user_id}")
    except Exception as e:
        return _tool_error(f"Send failed: {e}")


def _tool_ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _tool_error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


# ── Background monitor ─────────────────────────────────────────────

def _monitor_loop():
    # Only initialize cursor if it doesn't already exist
    if not CURSOR_FILE.exists() and INBOX_FILE.exists():
        lines = locked_read_lines(INBOX_FILE)
        _write_cursor(len(lines))
    elif not CURSOR_FILE.exists():
        _write_cursor(0)

    # Pre-populate pushed IDs from existing inbox to prevent replays
    if INBOX_FILE.exists():
        for line in locked_read_lines(INBOX_FILE):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                mid = str(msg.get("message_id", ""))
                if mid:
                    _pushed_ids.add(mid)
            except json.JSONDecodeError:
                pass

    _expired_notified = False

    while not _stop_event.is_set():
        time.sleep(2)
        if _stop_event.is_set():
            break

        # Check if daemon flagged session as expired
        if EXPIRED_FILE.exists() and not _expired_notified:
            _expired_notified = True
            _log("error", "WeChat session expired! Run: python -m openilink login")
            _channel_message(
                content="⚠️ WeChat session has expired. Please re-login:\n"
                        "1. Run `python -m openilink stop`\n"
                        "2. Run `python -m openilink login`\n"
                        "3. Run `python -m openilink start`",
                meta={"chat_id": "system", "user": "system", "ts": ""},
            )
        elif not EXPIRED_FILE.exists():
            _expired_notified = False  # reset if marker cleared

        try:
            for msg in _poll_new_messages():
                if msg.get("message_type") == 2:
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                msg_id = str(msg.get("message_id", ""))

                # Dedup: skip if already pushed
                if msg_id in _pushed_ids:
                    continue
                if len(_pushed_ids) > 10000:
                    _pushed_ids.clear()
                _pushed_ids.add(msg_id)

                user_id = msg.get("from_user_id", "")
                ctx_token = msg.get("context_token", "")
                ts = msg.get("ts", 0)
                iso_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""

                # Track as pending (for auto-ack timeout)
                if AUTO_ACK_TIMEOUT > 0 and ctx_token:
                    with _pending_lock:
                        _replied.discard(user_id)  # new message resets replied flag
                        _pending[user_id] = (time.time(), ctx_token, text)

                _channel_message(content=text, meta={
                    "chat_id": user_id,
                    "message_id": msg_id,
                    "user": user_id,
                    "user_id": user_id,
                    "ts": iso_ts,
                })
        except Exception as e:
            _log("error", f"Monitor: {e}")


def _auto_ack_loop():
    """Send a fallback reply if Claude doesn't respond within the timeout."""
    if AUTO_ACK_TIMEOUT <= 0:
        return  # disabled

    while True:
        time.sleep(5)
        now = time.time()
        expired: list[tuple[str, str]] = []

        with _pending_lock:
            for uid, (ts, ctx, _text) in list(_pending.items()):
                # Skip if Claude already replied via wechat_reply tool
                if uid in _replied:
                    del _pending[uid]
                    continue
                if now - ts >= AUTO_ACK_TIMEOUT:
                    expired.append((uid, ctx))
                    del _pending[uid]

        for uid, ctx in expired:
            # Re-check under lock right before sending to close the race
            # window between popping from pending and actually sending.
            with _pending_lock:
                if uid in _replied:
                    continue
            try:
                _send_reply_direct(uid, AUTO_ACK_MESSAGE, ctx)
                _log("info", f"Auto-ack sent to {uid} (Claude busy)")
            except Exception as e:
                _log("error", f"Auto-ack failed for {uid}: {e}")


def _send_reply_direct(user_id: str, text: str, ctx_token: str):
    """Send a reply bypassing the tool call (used for auto-ack)."""
    from openilink import Client
    state = _load_state()
    if not state.get("token"):
        return
    client = Client(token=state["token"])
    if state.get("base_url"):
        client.base_url = state["base_url"]
    client.send_text(user_id, text, ctx_token)


# ── MCP request router ─────────────────────────────────────────────

INSTRUCTIONS = (
    "The sender reads WeChat, not this session. Anything you want them to see "
    "must go through the reply tool — your transcript output never reaches their chat.\n\n"
    "Messages from WeChat arrive as "
    '<channel source="wechat" chat_id="..." message_id="..." user="..." ts="...">. '
    "Reply with the wechat_reply tool — pass chat_id back as user_id. "
    "Use reply_to (set to a message_id) only when replying to an earlier message; "
    "the latest message doesn't need a quote-reply, omit reply_to for normal responses.\n\n"
    "IMPORTANT: Call wechat_reply exactly ONCE per message — only with the actual reply content. "
    "Do NOT send a second message to confirm delivery (e.g. '已回复', 'Sent'). "
    "The tool return value already confirms success; any status text you output stays in this session.\n\n"
    "Reply in the same language as the message."
)

TOOLS = [{
    "name": "wechat_reply",
    "description": "Reply to a WeChat user. Pass the chat_id from the channel message as user_id.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "WeChat user ID (chat_id from channel message)"},
            "text": {"type": "string", "description": "Reply message text"},
        },
        "required": ["user_id", "text"],
    },
}]


def _handle(msg: dict):
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        _send_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "experimental": {"claude/channel": {}},
                "tools": {},
            },
            "serverInfo": {"name": "wechat-ilink", "version": "1.0.0"},
            "instructions": INSTRUCTIONS,
        })

    elif method == "notifications/initialized":
        if _ensure_daemon():
            _log("info", "WeChat iLink connected. Listening for messages.")
        else:
            _log("warning", "Not logged in. Run: python -m openilink login")

    elif method == "tools/list":
        _send_result(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "wechat_reply":
            _send_result(req_id, _do_reply(args.get("user_id", ""), args.get("text", "")))
        else:
            _send_result(req_id, _tool_error(f"Unknown tool: {name}"))

    elif method == "ping":
        _send_result(req_id, {})

    elif req_id is not None:
        _send_error(req_id, -32601, f"Method not found: {method}")


# ── Entry point ─────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    # Singleton: kill any old MCP server, then claim the PID
    _kill_old_mcp()
    _write_mcp_pid()

    # Handle graceful shutdown (from a newer MCP server taking over)
    def _on_stop(signum, frame):
        _stop_event.set()

    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    threading.Thread(target=_monitor_loop, daemon=True).start()
    threading.Thread(target=_auto_ack_loop, daemon=True).start()

    try:
        for line in sys.stdin:
            if _stop_event.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                _handle(json.loads(line))
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"[wechat-mcp] {e}", file=sys.stderr, flush=True)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        _cleanup_mcp_pid()


if __name__ == "__main__":
    main()
