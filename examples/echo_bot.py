"""Echo bot example - mirrors the Go echo-bot example."""

import signal
import sys
from pathlib import Path

from openilink import Client, LoginCallbacks, MonitorOptions, extract_text
from openilink.helpers import print_qrcode

SYNC_BUF_FILE = Path("sync_buf.dat")


def load_buf() -> str:
    try:
        return SYNC_BUF_FILE.read_text()
    except FileNotFoundError:
        return ""


def main():
    client = Client()

    print("Fetching QR code...")
    result = client.login_with_qr(
        callbacks=LoginCallbacks(
            on_qrcode=lambda url: (print("\nScan QR code with WeChat:"), print_qrcode(url)),
            on_scanned=lambda: print("Scanned, confirm on WeChat..."),
            on_expired=lambda attempt, mx: print(f"QR expired, refreshing ({attempt}/{mx})..."),
        )
    )

    if not result.connected:
        print(f"Login incomplete: {result.message}", file=sys.stderr)
        sys.exit(1)
    print(f"Connected! BotID={result.bot_id} UserID={result.user_id}\n")

    # Graceful shutdown on Ctrl+C
    def on_signal(sig, frame):
        print("\nStopping...")
        client.stop()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    def handler(msg):
        text = extract_text(msg)
        if not text:
            return
        print(f"[{msg.from_user_id}] {text}")
        try:
            client.push(msg.from_user_id, "echo: " + text)
        except Exception as e:
            print(f"Reply failed: {e}", file=sys.stderr)

    print("Listening for messages... (Ctrl+C to quit)")
    client.monitor(
        handler,
        opts=MonitorOptions(
            initial_buf=load_buf(),
            on_buf_update=lambda buf: SYNC_BUF_FILE.write_text(buf),
            on_error=lambda e: print(f"Error: {e}", file=sys.stderr),
        ),
    )


if __name__ == "__main__":
    main()
