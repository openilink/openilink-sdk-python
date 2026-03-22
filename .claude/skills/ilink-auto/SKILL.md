---
name: ilink-auto
description: Enable auto-reply mode for the iLink WeChat bot. Claude will automatically process incoming messages and reply intelligently.
disable-model-invocation: true
allowed-tools: Bash(python *)
---

# iLink Auto-Reply Mode

Start the auto-reply watcher. It monitors for new WeChat messages and uses Claude Code (`claude -p`) to generate intelligent replies automatically.

## Start auto-reply

```bash
python -m openilink auto
```

### Options

```bash
# Custom poll interval (default: 3 seconds)
python -m openilink auto --interval 5

# Custom Claude timeout per message (default: 120 seconds)
python -m openilink auto --timeout 60

# Custom system prompt
python -m openilink auto --prompt "你是一个客服助手，只回答产品相关问题"
```

## How it works

1. Polls `.ilink/inbox.jsonl` for new messages every N seconds
2. For each user message, calls `claude -p` with the message text
3. Captures Claude's response and sends it back via the SDK
4. Skips bot messages and empty messages

## Prerequisites

- Bot must be running: use `/ilink-start` first
- Claude Code CLI must be installed and authenticated

## Notes

- Press Ctrl+C to stop auto-reply
- Each message is processed independently (no conversation history)
- The auto cursor is separate from `/ilink-check` cursor
- Old messages are skipped on startup, only new messages are processed
