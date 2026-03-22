"""QR code login flow for the iLink Bot API."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import urljoin, quote

from .helpers import ensure_trailing_slash
from .types import LoginResult, QRCodeResponse, QRStatusResponse

if TYPE_CHECKING:
    from .client import Client

MAX_QR_REFRESH_COUNT = 3
QR_LONG_POLL_TIMEOUT = 40  # seconds
DEFAULT_LOGIN_TIMEOUT = 8 * 60  # 8 minutes


class LoginCallbacks:
    """Receives events during the QR login flow."""

    def __init__(
        self,
        on_qrcode: Optional[Callable[[str], None]] = None,
        on_scanned: Optional[Callable[[], None]] = None,
        on_expired: Optional[Callable[[int, int], None]] = None,
    ):
        self.on_qrcode = on_qrcode
        self.on_scanned = on_scanned
        self.on_expired = on_expired


def fetch_qr_code(client: Client) -> QRCodeResponse:
    """Request a new login QR code from the API."""
    base = ensure_trailing_slash(client.base_url)
    bot_type = client.bot_type or "3"
    url = urljoin(base, "ilink/bot/get_bot_qrcode") + "?bot_type=" + quote(bot_type)
    data = client._do_get(url, timeout=15)
    d = json.loads(data)
    return QRCodeResponse(
        qrcode=d.get("qrcode", ""),
        qrcode_img_content=d.get("qrcode_img_content", ""),
    )


def poll_qr_status(client: Client, qrcode: str) -> QRStatusResponse:
    """Poll the scan status of a QR code."""
    base = ensure_trailing_slash(client.base_url)
    url = urljoin(base, "ilink/bot/get_qrcode_status") + "?qrcode=" + quote(qrcode)
    headers = {"iLink-App-ClientVersion": "1"}
    try:
        data = client._do_get(url, extra_headers=headers, timeout=QR_LONG_POLL_TIMEOUT)
    except Exception:
        return QRStatusResponse(status="wait")
    d = json.loads(data)
    return QRStatusResponse(
        status=d.get("status", ""),
        bot_token=d.get("bot_token", ""),
        ilink_bot_id=d.get("ilink_bot_id", ""),
        baseurl=d.get("baseurl", ""),
        ilink_user_id=d.get("ilink_user_id", ""),
    )


def login_with_qr(
    client: Client,
    callbacks: Optional[LoginCallbacks] = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT,
) -> LoginResult:
    """Perform the full QR code login flow.

    On success the client's token and base_url are updated automatically.
    """
    if callbacks is None:
        callbacks = LoginCallbacks()

    deadline = time.monotonic() + timeout

    qr = fetch_qr_code(client)
    if callbacks.on_qrcode:
        callbacks.on_qrcode(qr.qrcode_img_content)

    scanned_notified = False
    refresh_count = 1
    current_qr = qr.qrcode

    while True:
        if time.monotonic() > deadline:
            return LoginResult(message="login timeout")

        status = poll_qr_status(client, current_qr)

        if status.status == "wait":
            pass

        elif status.status == "scaned":
            if not scanned_notified:
                scanned_notified = True
                if callbacks.on_scanned:
                    callbacks.on_scanned()

        elif status.status == "expired":
            refresh_count += 1
            if refresh_count > MAX_QR_REFRESH_COUNT:
                return LoginResult(message="QR code expired too many times")
            if callbacks.on_expired:
                callbacks.on_expired(refresh_count, MAX_QR_REFRESH_COUNT)
            new_qr = fetch_qr_code(client)
            current_qr = new_qr.qrcode
            scanned_notified = False
            if callbacks.on_qrcode:
                callbacks.on_qrcode(new_qr.qrcode_img_content)

        elif status.status == "confirmed":
            if not status.ilink_bot_id:
                return LoginResult(message="server did not return bot ID")
            if not status.baseurl:
                return LoginResult(
                    message="server did not return baseurl; "
                            "login succeeded but the session cannot be used"
                )
            client.token = status.bot_token
            client.base_url = status.baseurl
            return LoginResult(
                connected=True,
                bot_token=status.bot_token,
                bot_id=status.ilink_bot_id,
                base_url=status.baseurl,
                user_id=status.ilink_user_id,
                message="connected",
            )

        time.sleep(1)
