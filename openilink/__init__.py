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
    ENCRYPT_AES128_ECB,
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
    UploadResult,
    VideoItem,
    VoiceFormat,
    VoiceItem,
    WeixinMessage,
)
from .errors import APIError, HTTPError, NoContextTokenError
from .http import DefaultHTTPDoer, HTTPDoer, Response
from .helpers import extract_text, is_media_item, print_qrcode
from .crypto import (
    encrypt_aes_ecb,
    decrypt_aes_ecb,
    aes_ecb_padded_size,
    parse_aes_key,
)
from .mime import (
    mime_from_filename,
    extension_from_mime,
    is_image_mime,
    is_video_mime,
)
from .voice import build_wav, DEFAULT_VOICE_SAMPLE_RATE
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
    "ENCRYPT_AES128_ECB",
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
    "UploadResult",
    "VideoItem",
    "VoiceFormat",
    "VoiceItem",
    "WeixinMessage",
    # errors
    "APIError",
    "HTTPError",
    "NoContextTokenError",
    # http
    "HTTPDoer",
    "DefaultHTTPDoer",
    "Response",
    # crypto
    "encrypt_aes_ecb",
    "decrypt_aes_ecb",
    "aes_ecb_padded_size",
    "parse_aes_key",
    # mime
    "mime_from_filename",
    "extension_from_mime",
    "is_image_mime",
    "is_video_mime",
    # voice
    "build_wav",
    "DEFAULT_VOICE_SAMPLE_RATE",
    # helpers
    "extract_text",
    "is_media_item",
    "print_qrcode",
]
