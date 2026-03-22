---
name: ilink-reply
description: Reply to a WeChat user via iLink bot. Use when you need to send a message to a specific user.
argument-hint: <user_id> <message>
allowed-tools: Bash(python *)
---

# Reply to WeChat User

Send a message to a WeChat user through the iLink bot.

## Usage

```bash
python -m openilink send $ARGUMENTS
```

The first argument is the user_id, everything after is the message text.

## Notes

- The target user must have sent a message first (so a context token exists)
- If the send fails, check that the daemon is running with `python -m openilink status`
- Report the result to the user (success or failure)
