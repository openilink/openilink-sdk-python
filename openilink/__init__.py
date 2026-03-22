"""openilink-sdk-python - A Python client for the Weixin iLink Bot API.

The SDK covers the full lifecycle: QR-code login, long-poll message
monitoring, text/media sending, typing indicators, and proactive push.

Basic usage::

    from openilink import Client, LoginCallbacks, MonitorOptions, extract_text

    client = Client()
    result = client.login_with_qr()
    client.monitor(lambda msg: client.push(msg.from_user_id, "echo: " + extract_text(msg)))
"""

from .types import (
    BaseInfo,
    CDNMedia,
    FileItem,
    GetConfigResp,
    GetUpdatesResp,
    GetUploadURLResp,
    ImageItem,
    LoginResult,
    MessageItem,
    MessageItemType,
    MessageState,
    MessageType,
    QRCodeResponse,
    QRStatusResponse,
    RefMessage,
    TextItem,
    TypingStatus,
    UploadMediaType,
    VideoItem,
    VoiceItem,
    WeixinMessage,
)
from .errors import APIError, HTTPError, NoContextTokenError
from .helpers import extract_text
from .auth import LoginCallbacks
from .monitor import MonitorOptions

# Import Client last and attach high-level methods
from .client import Client as _Client
from . import auth as _auth
from . import monitor as _monitor


class Client(_Client):
    """Weixin iLink Bot API client with login and monitor support."""

    def login_with_qr(
        self,
        callbacks: LoginCallbacks | None = None,
        timeout: float = _auth.DEFAULT_LOGIN_TIMEOUT,
    ) -> LoginResult:
        """Perform the full QR code login flow.

        On success the client's token and base_url are updated automatically.
        """
        return _auth.login_with_qr(self, callbacks, timeout)

    def fetch_qr_code(self) -> QRCodeResponse:
        """Request a new login QR code from the API."""
        return _auth.fetch_qr_code(self)

    def poll_qr_status(self, qrcode: str) -> QRStatusResponse:
        """Poll the scan status of a QR code."""
        return _auth.poll_qr_status(self, qrcode)

    def monitor(
        self,
        handler,
        opts: MonitorOptions | None = None,
    ) -> None:
        """Run a long-poll loop, invoking handler for each inbound message.

        Blocks until client.stop() is called.
        """
        _monitor.monitor(self, handler, opts)


__all__ = [
    "Client",
    "LoginCallbacks",
    "MonitorOptions",
    # types
    "BaseInfo",
    "CDNMedia",
    "FileItem",
    "GetConfigResp",
    "GetUpdatesResp",
    "GetUploadURLResp",
    "ImageItem",
    "LoginResult",
    "MessageItem",
    "MessageItemType",
    "MessageState",
    "MessageType",
    "QRCodeResponse",
    "QRStatusResponse",
    "RefMessage",
    "TextItem",
    "TypingStatus",
    "UploadMediaType",
    "VideoItem",
    "VoiceItem",
    "WeixinMessage",
    # errors
    "APIError",
    "HTTPError",
    "NoContextTokenError",
    # helpers
    "extract_text",
]
