# openilink-sdk-python

Python SDK for the Weixin iLink Bot API.

## Install

```bash
pip install -e .
```

## Quick Start

```python
from openilink import Client, LoginCallbacks, MonitorOptions, extract_text

client = Client()

# QR code login
result = client.login_with_qr(
    callbacks=LoginCallbacks(
        on_qrcode=lambda url: print(f"Scan: {url}"),
        on_scanned=lambda: print("Scanned!"),
    )
)
print(f"Connected: BotID={result.bot_id}")

# Echo bot
client.monitor(
    lambda msg: client.push(msg.from_user_id, "echo: " + extract_text(msg)),
    opts=MonitorOptions(
        on_error=lambda e: print(f"Error: {e}"),
    ),
)
```

## API

| Method | Description |
|---|---|
| `Client(token, base_url, ...)` | Create client |
| `client.login_with_qr(callbacks)` | QR code login |
| `client.monitor(handler, opts)` | Long-poll message loop |
| `client.send_text(to, text, context_token)` | Send text message |
| `client.push(to, text)` | Send with cached context token |
| `client.send_typing(user_id, ticket, status)` | Typing indicator |
| `client.get_config(user_id, context_token)` | Get bot config |
| `client.get_upload_url(req)` | Get CDN upload URL |
| `client.stop()` | Stop monitor loop |
| `extract_text(msg)` | Extract first text from message |
