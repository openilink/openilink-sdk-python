---
name: ilink-stop
description: Stop the iLink WeChat bot daemon.
disable-model-invocation: true
allowed-tools: Bash(python *)
---

# Stop iLink WeChat Bot

Stop the running iLink daemon.

```bash
python -m openilink stop
```

Then verify:

```bash
python -m openilink status
```
