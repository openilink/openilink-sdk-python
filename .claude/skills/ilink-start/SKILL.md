---
name: ilink-start
description: Start the iLink WeChat bot. Login via QR code and begin monitoring messages.
disable-model-invocation: true
allowed-tools: Bash(python *)
---

# Start iLink WeChat Bot

Start the iLink WeChat bot daemon to receive and send WeChat messages.

## Steps

1. First check if already logged in:

```bash
python -m openilink status
```

2. If not logged in, run the interactive login (user needs to scan QR code):

```bash
python -m openilink login
```

3. After login succeeds, start the background daemon:

```bash
python -m openilink start
```

4. Verify the daemon is running:

```bash
python -m openilink status
```

5. Tell the user:
   - The bot is now running in the background
   - Use `/ilink-check` to see new messages
   - Use `/ilink-reply <user_id> <message>` to reply
   - Use `/ilink-auto` to enable auto-reply mode
   - Use `/ilink-stop` to stop the bot
