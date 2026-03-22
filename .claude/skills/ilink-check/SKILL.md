---
name: ilink-check
description: Check for new WeChat messages from the iLink bot. Use when the user asks about new messages or wants to see what's been received.
allowed-tools: Bash(python *)
---

# Check New WeChat Messages

Fetch and display unread messages from the iLink bot inbox.

```bash
python -m openilink check
```

The output is a JSON array of messages. Each message has:
- `from_user_id` — who sent the message
- `text` — the message content
- `ts` — timestamp
- `context_token` — needed for replies (handled automatically)

## After checking

- Show the messages to the user in a readable format
- If the user wants to reply, use `/ilink-reply <user_id> <message>`
- If there are no new messages, let the user know
