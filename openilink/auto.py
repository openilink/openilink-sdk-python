"""Auto-reply: monitor inbox and use Claude Code to process and reply."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .daemon import ILINK_DIR, INBOX_FILE, _ensure_dir, load_state

AUTO_CURSOR_FILE = ILINK_DIR / "auto_cursor"
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_CLAUDE_TIMEOUT = 120

DEFAULT_SYSTEM_PROMPT = (
    "你是一个微信智能助手。用户通过微信给你发了一条消息。\n"
    "请根据消息内容给出有帮助的回复。\n"
    "要求：\n"
    "- 使用和用户相同的语言\n"
    "- 简洁友好，不超过500字\n"
    "- 直接输出回复内容，不要加任何前缀、解释或格式标记\n"
    "- 如果是问题，直接回答\n"
    "- 如果是打招呼，热情回应"
)


def _read_auto_cursor() -> int:
    try:
        return int(AUTO_CURSOR_FILE.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return 0


def _write_auto_cursor(n: int):
    try:
        _ensure_dir()
        AUTO_CURSOR_FILE.write_text(str(n))
    except OSError:
        pass  # best-effort; don't crash on write failure


def _get_new_messages() -> list[dict]:
    """Read unprocessed messages from inbox, advance cursor."""
    if not INBOX_FILE.exists():
        return []

    cursor = _read_auto_cursor()
    messages: list[dict] = []
    total = 0

    with open(INBOX_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            total = i + 1
            if i < cursor:
                continue
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip malformed lines

    _write_auto_cursor(total)
    return messages


def _invoke_claude(prompt: str, timeout: float) -> str | None:
    """Call claude CLI and return response text, or None on failure."""
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        print("[auto] ERROR: 'claude' not found in PATH.", file=sys.stderr, flush=True)
        print("[auto] Install: npm install -g @anthropic-ai/claude-code", file=sys.stderr, flush=True)
        return None

    try:
        result = subprocess.run(
            [claude_cmd, "-p", prompt, "--no-input"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"[auto] Claude timed out ({timeout}s)", file=sys.stderr, flush=True)
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()[:200] if result.stderr else ""
        print(f"[auto] Claude error (rc={result.returncode}): {stderr}",
              file=sys.stderr, flush=True)
        return None

    return result.stdout.strip() or None


def _send_reply(user_id: str, text: str, context_token: str) -> bool:
    """Send a reply using the SDK. Returns True on success."""
    from . import Client

    state = load_state()
    if not state.get("token"):
        print("[auto] No token, cannot send.", file=sys.stderr, flush=True)
        return False

    try:
        client = Client(token=state["token"])
        if state.get("base_url"):
            client.base_url = state["base_url"]
        client.send_text(user_id, text, context_token)
        return True
    except Exception as e:
        print(f"[auto] Send failed: {e}", file=sys.stderr, flush=True)
        return False


def run_auto(
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    claude_timeout: float = DEFAULT_CLAUDE_TIMEOUT,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> None:
    """Main auto-reply loop."""
    # Verify login state
    state = load_state()
    if not state.get("token"):
        print("Not logged in. Run 'python -m openilink login' first.", file=sys.stderr)
        sys.exit(1)

    # Verify claude is available
    if not shutil.which("claude"):
        print("'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code",
              file=sys.stderr)
        sys.exit(1)

    _ensure_dir()

    # Skip existing messages on startup
    if INBOX_FILE.exists():
        with open(INBOX_FILE, encoding="utf-8") as f:
            total = sum(1 for _ in f)
        _write_auto_cursor(total)
        print(f"[auto] Skipped {total} existing messages")

    print(f"[auto] Auto-reply started (poll={poll_interval}s, timeout={claude_timeout}s)")
    print("[auto] Waiting for new messages... (Ctrl+C to stop)\n")

    try:
        while True:
            messages = _get_new_messages()
            for msg in messages:
                # Skip bot messages and empty text
                if msg.get("message_type") == 2:
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                user_id = msg.get("from_user_id", "")
                ctx_token = msg.get("context_token", "")
                if not ctx_token:
                    print(f"[auto] No context_token for {user_id}, skip", flush=True)
                    continue

                print(f"[auto] << {user_id}: {text}", flush=True)

                # Build prompt and call Claude
                prompt = f"{system_prompt}\n\n用户消息：{text}"
                reply = _invoke_claude(prompt, claude_timeout)

                if not reply:
                    print(f"[auto] No reply generated, skip", flush=True)
                    continue

                # Send reply
                ok = _send_reply(user_id, reply, ctx_token)
                if ok:
                    print(f"[auto] >> {user_id}: {reply[:100]}{'...' if len(reply) > 100 else ''}",
                          flush=True)
                print(flush=True)

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n[auto] Stopped.")
