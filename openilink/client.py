"""Core client for the Weixin iLink Bot API."""

from __future__ import annotations

import hashlib
import json
import os
import time
import threading
from typing import Any, Callable, Optional
from urllib.parse import urljoin, quote, urlencode
from urllib.error import URLError

from .errors import APIError, HTTPError, NoContextTokenError
from .helpers import ensure_trailing_slash, random_wechat_uin
from .http import DefaultHTTPDoer, HTTPDoer
from .types import (
    ENCRYPT_AES128_ECB,
    CDNMedia,
    FileItem,
    GetConfigResp,
    GetUpdatesResp,
    GetUploadURLResp,
    ImageItem,
    MessageItemType,
    MessageState,
    MessageType,
    TypingStatus,
    UploadMediaType,
    UploadResult,
    VideoItem,
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
        version: str = "1.0.2",
        route_tag: str = "",
        http_doer: Optional[HTTPDoer] = None,
        silk_decoder: Optional[Callable[[bytes, int], bytes]] = None,
    ):
        self.base_url = base_url
        self.cdn_base_url = cdn_base_url
        self.token = token
        self.bot_type = bot_type
        self.version = version
        self.route_tag = route_tag
        self.silk_decoder = silk_decoder
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
        if self.route_tag:
            headers["SKRouteTag"] = self.route_tag
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
        client_id = f"sdk-{int.from_bytes(os.urandom(8), 'big'):016x}"
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

    # --- CDN upload / download ---

    _UPLOAD_MAX_RETRIES = 3
    _CDN_TIMEOUT = 60

    def _build_cdn_download_url(self, encrypted_query_param: str) -> str:
        return self.cdn_base_url + "/download?encrypted_query_param=" + quote(encrypted_query_param)

    def _build_cdn_upload_url(self, upload_param: str, filekey: str) -> str:
        return (
            self.cdn_base_url + "/upload?encrypted_query_param=" + quote(upload_param)
            + "&filekey=" + quote(filekey)
        )

    def _upload_to_cdn(self, cdn_url: str, ciphertext: bytes) -> str:
        """Upload with retry, return download encrypted_query_param."""
        last_err: Optional[Exception] = None
        for attempt in range(1, self._UPLOAD_MAX_RETRIES + 1):
            try:
                download_param = self._do_cdn_post(cdn_url, ciphertext)
                return download_param
            except HTTPError as e:
                last_err = e
                if 400 <= e.status_code < 500:
                    raise
            except Exception as e:
                last_err = e
            if attempt < self._UPLOAD_MAX_RETRIES:
                time.sleep(2)
        raise RuntimeError(f"CDN upload failed after {self._UPLOAD_MAX_RETRIES} attempts: {last_err}")

    def _do_cdn_post(self, cdn_url: str, body: bytes) -> str:
        """Low-level CDN POST that extracts x-encrypted-param from response."""
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError as _URLHTTPError
        import ssl

        req = Request(cdn_url, data=body, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        if self.route_tag:
            req.add_header("SKRouteTag", self.route_tag)

        ctx = ssl.create_default_context()
        try:
            with urlopen(req, timeout=self._CDN_TIMEOUT, context=ctx) as resp:
                download_param = resp.headers.get("x-encrypted-param", "")
                resp.read()  # drain body
        except _URLHTTPError as e:
            err_msg = ""
            try:
                err_msg = e.headers.get("x-error-message", "") or e.read().decode(errors="replace")
            except Exception:
                pass
            raise HTTPError(e.code, err_msg.encode() if err_msg else b"") from e

        if not download_param:
            raise RuntimeError("CDN response missing x-encrypted-param header")
        return download_param

    def upload_file(
        self,
        plaintext: bytes,
        to_user_id: str,
        media_type: UploadMediaType,
    ) -> UploadResult:
        """Upload a file to the Weixin CDN with AES-128-ECB encryption.

        Handles the full pipeline: MD5 hash, AES key generation, getUploadUrl
        API call, encryption, and CDN POST with retry.
        """
        from .crypto import encrypt_aes_ecb, aes_ecb_padded_size

        raw_size = len(plaintext)
        raw_md5 = hashlib.md5(plaintext).hexdigest()
        file_size = aes_ecb_padded_size(raw_size)
        filekey = os.urandom(16).hex()
        aes_key = os.urandom(16)

        # 1. Get pre-signed upload URL
        upload_resp = self.get_upload_url({
            "filekey": filekey,
            "media_type": int(media_type),
            "to_user_id": to_user_id,
            "rawsize": raw_size,
            "rawfilemd5": raw_md5,
            "filesize": file_size,
            "no_need_thumb": True,
            "aeskey": aes_key.hex(),
        })
        if not upload_resp.upload_param:
            raise RuntimeError("getUploadUrl returned no upload_param")

        # 2. Encrypt
        ciphertext = encrypt_aes_ecb(plaintext, aes_key)

        # 3. Upload to CDN with retry
        cdn_url = self._build_cdn_upload_url(upload_resp.upload_param, filekey)
        download_param = self._upload_to_cdn(cdn_url, ciphertext)

        return UploadResult(
            file_key=filekey,
            download_encrypted_query_param=download_param,
            aes_key=aes_key.hex(),
            file_size=raw_size,
            ciphertext_size=len(ciphertext),
        )

    def download_file(self, encrypted_query_param: str, aes_key_base64: str) -> bytes:
        """Download and decrypt a file from the Weixin CDN."""
        from .crypto import parse_aes_key, decrypt_aes_ecb

        key = parse_aes_key(aes_key_base64)
        dl_url = self._build_cdn_download_url(encrypted_query_param)
        extra = {"SKRouteTag": self.route_tag} if self.route_tag else None
        ciphertext = self._do_get(dl_url, extra_headers=extra, timeout=self._CDN_TIMEOUT)
        return decrypt_aes_ecb(ciphertext, key)

    def download_raw(self, encrypted_query_param: str) -> bytes:
        """Download raw bytes from CDN without decryption."""
        dl_url = self._build_cdn_download_url(encrypted_query_param)
        extra = {"SKRouteTag": self.route_tag} if self.route_tag else None
        return self._do_get(dl_url, extra_headers=extra, timeout=self._CDN_TIMEOUT)

    # --- Media send methods ---

    @staticmethod
    def _media_aes_key(hex_key: str) -> str:
        """Convert hex AES key to base64(hex) format used in CDNMedia."""
        import base64
        return base64.b64encode(hex_key.encode()).decode()

    def _generate_client_id(self) -> str:
        return f"sdk-{int.from_bytes(os.urandom(8), 'big'):016x}"

    def send_image(
        self, to: str, context_token: str, uploaded: UploadResult,
    ) -> str:
        """Send an image message. Use upload_file() with IMAGE first."""
        client_id = self._generate_client_id()
        msg = {
            "msg": {
                "to_user_id": to,
                "client_id": client_id,
                "message_type": int(MessageType.BOT),
                "message_state": int(MessageState.FINISH),
                "context_token": context_token,
                "item_list": [{
                    "type": int(MessageItemType.IMAGE),
                    "image_item": {
                        "media": {
                            "encrypt_query_param": uploaded.download_encrypted_query_param,
                            "aes_key": self._media_aes_key(uploaded.aes_key),
                            "encrypt_type": ENCRYPT_AES128_ECB,
                        },
                        "mid_size": uploaded.ciphertext_size,
                    },
                }],
            },
        }
        self.send_message(msg)
        return client_id

    def send_video(
        self, to: str, context_token: str, uploaded: UploadResult,
    ) -> str:
        """Send a video message. Use upload_file() with VIDEO first."""
        client_id = self._generate_client_id()
        msg = {
            "msg": {
                "to_user_id": to,
                "client_id": client_id,
                "message_type": int(MessageType.BOT),
                "message_state": int(MessageState.FINISH),
                "context_token": context_token,
                "item_list": [{
                    "type": int(MessageItemType.VIDEO),
                    "video_item": {
                        "media": {
                            "encrypt_query_param": uploaded.download_encrypted_query_param,
                            "aes_key": self._media_aes_key(uploaded.aes_key),
                            "encrypt_type": ENCRYPT_AES128_ECB,
                        },
                        "video_size": uploaded.ciphertext_size,
                    },
                }],
            },
        }
        self.send_message(msg)
        return client_id

    def send_file_attachment(
        self, to: str, context_token: str, file_name: str, uploaded: UploadResult,
    ) -> str:
        """Send a file attachment message. Use upload_file() with FILE first."""
        client_id = self._generate_client_id()
        msg = {
            "msg": {
                "to_user_id": to,
                "client_id": client_id,
                "message_type": int(MessageType.BOT),
                "message_state": int(MessageState.FINISH),
                "context_token": context_token,
                "item_list": [{
                    "type": int(MessageItemType.FILE),
                    "file_item": {
                        "media": {
                            "encrypt_query_param": uploaded.download_encrypted_query_param,
                            "aes_key": self._media_aes_key(uploaded.aes_key),
                            "encrypt_type": ENCRYPT_AES128_ECB,
                        },
                        "file_name": file_name,
                        "len": str(uploaded.file_size),
                    },
                }],
            },
        }
        self.send_message(msg)
        return client_id

    def send_media_file(
        self,
        to: str,
        context_token: str,
        data: bytes,
        file_name: str,
        caption: str = "",
    ) -> None:
        """High-level helper: upload and send a media file.

        Auto-detects media type (image/video/file) from filename.
        Optionally sends a caption text before the media.
        """
        from .mime import mime_from_filename, is_image_mime, is_video_mime

        mime = mime_from_filename(file_name)
        if is_video_mime(mime):
            media_type = UploadMediaType.VIDEO
        elif is_image_mime(mime):
            media_type = UploadMediaType.IMAGE
        else:
            media_type = UploadMediaType.FILE

        uploaded = self.upload_file(data, to, media_type)

        if caption:
            self.send_text(to, caption, context_token)

        if is_video_mime(mime):
            self.send_video(to, context_token, uploaded)
        elif is_image_mime(mime):
            self.send_image(to, context_token, uploaded)
        else:
            self.send_file_attachment(to, context_token, os.path.basename(file_name), uploaded)

    def download_voice(self, voice_item) -> bytes:
        """Download a voice message, decode SILK, return WAV bytes.

        Requires silk_decoder to be set on the client.
        """
        from .voice import download_voice
        return download_voice(self, voice_item, silk_decoder=self.silk_decoder)

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
        sync_buf=d.get("sync_buf", ""),
        longpolling_timeout_ms=d.get("longpolling_timeout_ms", 0),
    )
