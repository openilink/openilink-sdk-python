"""Core client for the Weixin iLink Bot API."""

from __future__ import annotations

import json
import time
import threading
from typing import Any, Optional
from urllib.parse import urljoin, quote
from urllib.error import URLError

from .errors import APIError, HTTPError, NoContextTokenError
from .helpers import ensure_trailing_slash, random_wechat_uin
from .http import DefaultHTTPDoer, HTTPDoer
from .types import (
    GetConfigResp,
    GetUpdatesResp,
    GetUploadURLResp,
    MessageState,
    MessageType,
    TypingStatus,
)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_BOT_TYPE = "3"

_DEFAULT_LONG_POLL_TIMEOUT = 35
_DEFAULT_API_TIMEOUT = 15
_DEFAULT_CONFIG_TIMEOUT = 10


class Client:
    """Communicates with the Weixin iLink Bot API.

    Basic usage::

        client = Client("")
        result = client.login_with_qr()
        client.monitor(handler)
    """

    def __init__(
        self,
        token: str = "",
        *,
        base_url: str = DEFAULT_BASE_URL,
        cdn_base_url: str = DEFAULT_CDN_BASE_URL,
        bot_type: str = DEFAULT_BOT_TYPE,
        version: str = "1.0.0",
        http_doer: Optional[HTTPDoer] = None,
    ):
        self.base_url = base_url
        self.cdn_base_url = cdn_base_url
        self.token = token
        self.bot_type = bot_type
        self.version = version
        self._http = http_doer or DefaultHTTPDoer()
        self._context_tokens: dict[str, str] = {}
        self._ctx_lock = threading.Lock()
        self._stop_event = threading.Event()

    # --- context token cache ---

    def set_context_token(self, user_id: str, token: str) -> None:
        with self._ctx_lock:
            self._context_tokens[user_id] = token

    def get_context_token(self, user_id: str) -> Optional[str]:
        with self._ctx_lock:
            return self._context_tokens.get(user_id)

    # --- internal helpers ---

    def _build_base_info(self) -> dict:
        return {"channel_version": self.version}

    def _build_headers(self, body: bytes) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body)),
            "X-WECHAT-UIN": random_wechat_uin(),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _do_post(self, endpoint: str, body: Any, timeout: float) -> bytes:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        base = ensure_trailing_slash(self.base_url)
        url = urljoin(base, endpoint)
        headers = self._build_headers(data)
        resp = self._http.do("POST", url, headers=headers, body=data, timeout=timeout)
        if resp.status_code >= 400:
            raise HTTPError(resp.status_code, resp.content)
        return resp.content

    def _do_get(
        self,
        url: str,
        extra_headers: Optional[dict[str, str]] = None,
        timeout: float = 15,
    ) -> bytes:
        resp = self._http.do("GET", url, headers=extra_headers, timeout=timeout)
        if resp.status_code >= 400:
            raise HTTPError(resp.status_code, resp.content)
        return resp.content

    # --- API methods ---

    def get_updates(self, get_updates_buf: str = "") -> GetUpdatesResp:
        """Long-poll for new messages. Returns empty response on timeout."""
        req_body = {
            "get_updates_buf": get_updates_buf,
            "base_info": self._build_base_info(),
        }
        timeout = _DEFAULT_LONG_POLL_TIMEOUT + 5
        try:
            data = self._do_post("ilink/bot/getupdates", req_body, timeout)
        except (URLError, OSError):
            return GetUpdatesResp(ret=0, get_updates_buf=get_updates_buf)

        return _parse_get_updates_resp(data)

    def send_message(self, msg: dict) -> None:
        """Send a raw message request."""
        msg["base_info"] = self._build_base_info()
        self._do_post("ilink/bot/sendmessage", msg, _DEFAULT_API_TIMEOUT)

    def send_text(self, to: str, text: str, context_token: str) -> str:
        """Send a plain text message. Returns the client_id."""
        client_id = f"sdk-{int(time.time() * 1000)}"
        msg = {
            "msg": {
                "to_user_id": to,
                "client_id": client_id,
                "message_type": int(MessageType.BOT),
                "message_state": int(MessageState.FINISH),
                "context_token": context_token,
                "item_list": [
                    {"type": 1, "text_item": {"text": text}},
                ],
            },
        }
        self.send_message(msg)
        return client_id

    def get_config(self, user_id: str, context_token: str) -> GetConfigResp:
        """Fetch bot config (includes typing_ticket) for a user."""
        req_body = {
            "ilink_user_id": user_id,
            "context_token": context_token,
            "base_info": self._build_base_info(),
        }
        data = self._do_post("ilink/bot/getconfig", req_body, _DEFAULT_CONFIG_TIMEOUT)
        try:
            d = json.loads(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise APIError(
                ret=-1, errcode=-1,
                errmsg=f"get_config: invalid JSON response: {exc}",
            ) from exc
        return GetConfigResp(
            ret=d.get("ret", 0),
            errmsg=d.get("errmsg", ""),
            typing_ticket=d.get("typing_ticket", ""),
        )

    def send_typing(
        self, user_id: str, typing_ticket: str, status: TypingStatus = TypingStatus.TYPING
    ) -> None:
        """Send or cancel a typing indicator."""
        req_body = {
            "ilink_user_id": user_id,
            "typing_ticket": typing_ticket,
            "status": int(status),
            "base_info": self._build_base_info(),
        }
        self._do_post("ilink/bot/sendtyping", req_body, _DEFAULT_CONFIG_TIMEOUT)

    def get_upload_url(self, req: dict) -> GetUploadURLResp:
        """Request a pre-signed CDN upload URL."""
        req["base_info"] = self._build_base_info()
        data = self._do_post("ilink/bot/getuploadurl", req, _DEFAULT_API_TIMEOUT)
        try:
            d = json.loads(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise APIError(
                ret=-1, errcode=-1,
                errmsg=f"get_upload_url: invalid JSON response: {exc}",
            ) from exc
        return GetUploadURLResp(
            upload_param=d.get("upload_param", ""),
            thumb_upload_param=d.get("thumb_upload_param", ""),
        )

    def push(self, to: str, text: str) -> str:
        """Send a proactive text message using a cached context token.

        The target user must have previously sent a message so that a context
        token is available. Raises NoContextTokenError otherwise.
        """
        token = self.get_context_token(to)
        if token is None:
            raise NoContextTokenError()
        return self.send_text(to, text, token)

    # --- stop control ---

    def stop(self) -> None:
        """Signal the monitor loop to stop."""
        self._stop_event.set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()


# ---------- Parsing helpers ----------

def _safe_enum(enum_cls, value, default=None):
    """Convert *value* to *enum_cls*, returning *default* on unknown values."""
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default if default is not None else value


def _parse_cdn_media(d: Optional[dict]) -> Any:
    if not d:
        return None
    from .types import CDNMedia
    return CDNMedia(
        encrypt_query_param=d.get("encrypt_query_param", ""),
        aes_key=d.get("aes_key", ""),
        encrypt_type=d.get("encrypt_type", 0),
    )


def _parse_message_item(d: dict) -> Any:
    from .types import (
        MessageItemType, TextItem, ImageItem, VoiceItem, FileItem, VideoItem,
        RefMessage, MessageItem as MI,
    )
    text_item = None
    if d.get("text_item"):
        text_item = TextItem(text=d["text_item"].get("text", ""))

    image_item = None
    if d.get("image_item"):
        img = d["image_item"]
        image_item = ImageItem(
            media=_parse_cdn_media(img.get("media")),
            thumb_media=_parse_cdn_media(img.get("thumb_media")),
            aeskey=img.get("aeskey", ""),
            url=img.get("url", ""),
            mid_size=img.get("mid_size", 0),
            thumb_size=img.get("thumb_size", 0),
            thumb_height=img.get("thumb_height", 0),
            thumb_width=img.get("thumb_width", 0),
            hd_size=img.get("hd_size", 0),
        )

    voice_item = None
    if d.get("voice_item"):
        v = d["voice_item"]
        voice_item = VoiceItem(
            media=_parse_cdn_media(v.get("media")),
            encode_type=v.get("encode_type", 0),
            bits_per_sample=v.get("bits_per_sample", 0),
            sample_rate=v.get("sample_rate", 0),
            playtime=v.get("playtime", 0),
            text=v.get("text", ""),
        )

    file_item = None
    if d.get("file_item"):
        f = d["file_item"]
        file_item = FileItem(
            media=_parse_cdn_media(f.get("media")),
            file_name=f.get("file_name", ""),
            md5=f.get("md5", ""),
            len=f.get("len", ""),
        )

    video_item = None
    if d.get("video_item"):
        vi = d["video_item"]
        video_item = VideoItem(
            media=_parse_cdn_media(vi.get("media")),
            video_size=vi.get("video_size", 0),
            play_length=vi.get("play_length", 0),
            video_md5=vi.get("video_md5", ""),
            thumb_media=_parse_cdn_media(vi.get("thumb_media")),
            thumb_size=vi.get("thumb_size", 0),
            thumb_height=vi.get("thumb_height", 0),
            thumb_width=vi.get("thumb_width", 0),
        )

    ref_msg = None
    if d.get("ref_msg"):
        r = d["ref_msg"]
        ref_msg = RefMessage(
            message_item=_parse_message_item(r["message_item"]) if r.get("message_item") else None,
            title=r.get("title", ""),
        )

    return MI(
        type=_safe_enum(MessageItemType, d.get("type", 0), MessageItemType.NONE),
        create_time_ms=d.get("create_time_ms", 0),
        update_time_ms=d.get("update_time_ms", 0),
        is_completed=d.get("is_completed", False),
        msg_id=d.get("msg_id", ""),
        ref_msg=ref_msg,
        text_item=text_item,
        image_item=image_item,
        voice_item=voice_item,
        file_item=file_item,
        video_item=video_item,
    )


def _parse_weixin_message(d: dict) -> Any:
    from .types import WeixinMessage, MessageType, MessageState
    items = [_parse_message_item(i) for i in d.get("item_list", [])]
    return WeixinMessage(
        seq=d.get("seq", 0),
        message_id=d.get("message_id", 0),
        from_user_id=d.get("from_user_id", ""),
        to_user_id=d.get("to_user_id", ""),
        client_id=d.get("client_id", ""),
        create_time_ms=d.get("create_time_ms", 0),
        update_time_ms=d.get("update_time_ms", 0),
        delete_time_ms=d.get("delete_time_ms", 0),
        session_id=d.get("session_id", ""),
        group_id=d.get("group_id", ""),
        message_type=_safe_enum(MessageType, d.get("message_type", 0), MessageType.NONE),
        message_state=_safe_enum(MessageState, d.get("message_state", 0), MessageState.NEW),
        item_list=items,
        context_token=d.get("context_token", ""),
    )


def _parse_get_updates_resp(data: bytes) -> GetUpdatesResp:
    try:
        d = json.loads(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise APIError(
            ret=-1, errcode=-1,
            errmsg=f"get_updates: invalid JSON response: {exc}",
        ) from exc
    msgs = [_parse_weixin_message(m) for m in d.get("msgs", [])]
    return GetUpdatesResp(
        ret=d.get("ret", 0),
        errcode=d.get("errcode", 0),
        errmsg=d.get("errmsg", ""),
        msgs=msgs,
        get_updates_buf=d.get("get_updates_buf", ""),
        longpolling_timeout_ms=d.get("longpolling_timeout_ms", 0),
    )
