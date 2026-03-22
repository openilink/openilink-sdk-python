"""Data types for the openilink SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


# ---------- Enums ----------

class UploadMediaType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class MessageType(IntEnum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageItemType(IntEnum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageState(IntEnum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


class TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


# ---------- Data classes ----------

@dataclass
class BaseInfo:
    channel_version: str = ""


@dataclass
class CDNMedia:
    encrypt_query_param: str = ""
    aes_key: str = ""
    encrypt_type: int = 0


@dataclass
class TextItem:
    text: str = ""


@dataclass
class ImageItem:
    media: Optional[CDNMedia] = None
    thumb_media: Optional[CDNMedia] = None
    aeskey: str = ""
    url: str = ""
    mid_size: int = 0
    thumb_size: int = 0
    thumb_height: int = 0
    thumb_width: int = 0
    hd_size: int = 0


@dataclass
class VoiceItem:
    media: Optional[CDNMedia] = None
    encode_type: int = 0
    bits_per_sample: int = 0
    sample_rate: int = 0
    playtime: int = 0
    text: str = ""


@dataclass
class FileItem:
    media: Optional[CDNMedia] = None
    file_name: str = ""
    md5: str = ""
    len: str = ""


@dataclass
class VideoItem:
    media: Optional[CDNMedia] = None
    video_size: int = 0
    play_length: int = 0
    video_md5: str = ""
    thumb_media: Optional[CDNMedia] = None
    thumb_size: int = 0
    thumb_height: int = 0
    thumb_width: int = 0


@dataclass
class RefMessage:
    message_item: Optional[MessageItem] = None
    title: str = ""


@dataclass
class MessageItem:
    type: MessageItemType = MessageItemType.NONE
    create_time_ms: int = 0
    update_time_ms: int = 0
    is_completed: bool = False
    msg_id: str = ""
    ref_msg: Optional[RefMessage] = None
    text_item: Optional[TextItem] = None
    image_item: Optional[ImageItem] = None
    voice_item: Optional[VoiceItem] = None
    file_item: Optional[FileItem] = None
    video_item: Optional[VideoItem] = None


# Fix forward reference
RefMessage.__dataclass_fields__["message_item"].default = None


@dataclass
class WeixinMessage:
    seq: int = 0
    message_id: int = 0
    from_user_id: str = ""
    to_user_id: str = ""
    client_id: str = ""
    create_time_ms: int = 0
    update_time_ms: int = 0
    delete_time_ms: int = 0
    session_id: str = ""
    group_id: str = ""
    message_type: MessageType = MessageType.NONE
    message_state: MessageState = MessageState.NEW
    item_list: list[MessageItem] = field(default_factory=list)
    context_token: str = ""


@dataclass
class GetUpdatesResp:
    ret: int = 0
    errcode: int = 0
    errmsg: str = ""
    msgs: list[WeixinMessage] = field(default_factory=list)
    get_updates_buf: str = ""
    longpolling_timeout_ms: int = 0


@dataclass
class GetConfigResp:
    ret: int = 0
    errmsg: str = ""
    typing_ticket: str = ""


@dataclass
class GetUploadURLResp:
    upload_param: str = ""
    thumb_upload_param: str = ""


@dataclass
class QRCodeResponse:
    qrcode: str = ""
    qrcode_img_content: str = ""


@dataclass
class QRStatusResponse:
    status: str = ""  # wait, scaned, confirmed, expired
    bot_token: str = ""
    ilink_bot_id: str = ""
    baseurl: str = ""
    ilink_user_id: str = ""


@dataclass
class LoginResult:
    connected: bool = False
    bot_token: str = ""
    bot_id: str = ""
    base_url: str = ""
    user_id: str = ""
    message: str = ""
