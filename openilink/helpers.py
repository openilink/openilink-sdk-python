"""Utility functions for the openilink SDK."""

from __future__ import annotations

import base64
import os
import struct

from .types import MessageItemType, WeixinMessage


def ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def random_wechat_uin() -> str:
    n = struct.unpack(">I", os.urandom(4))[0]
    return base64.b64encode(str(n).encode()).decode()


def extract_text(msg: WeixinMessage) -> str:
    """Return the first text body from a message's item list."""
    for item in msg.item_list:
        if item.type == MessageItemType.TEXT and item.text_item is not None:
            return item.text_item.text
    return ""
