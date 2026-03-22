---
name: ilink-reconnect
description: Reconnect WeChat by logging out and logging back in. Use when the user wants to re-login, refresh the QR code, or fix a broken WeChat connection.
allowed-tools: Bash(python *)
---

# Reconnect WeChat

Logout the current session and start a fresh QR login.

## Step 1 — Logout

```bash
python -m openilink logout
```

## Step 2 — Login

The login command requires interactive QR scanning, so the user must run it themselves:

Tell the user to run this command in their terminal:

```
! python -m openilink login
```

Explain that they need to scan the QR code with WeChat to complete the login.

## Notes

- Do NOT run `python -m openilink login` directly — it requires interactive input (QR scan)
- After login succeeds, the MCP server will auto-detect the new token and start the daemon
- If the user just wants to restart the daemon without re-login, suggest `python -m openilink stop && python -m openilink start` instead
