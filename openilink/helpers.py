"""Utility functions for the openilink SDK."""

from __future__ import annotations

import base64
import io
import os
import struct

from .types import MessageItemType, WeixinMessage


def ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def random_wechat_uin() -> str:
    n = struct.unpack(">I", os.urandom(4))[0]
    return base64.b64encode(str(n).encode()).decode()


def is_media_item(item) -> bool:
    """Check if a message item is a media type (image, video, file, or voice)."""
    return item.type in (
        MessageItemType.IMAGE,
        MessageItemType.VIDEO,
        MessageItemType.FILE,
        MessageItemType.VOICE,
    )


def extract_text(msg: WeixinMessage) -> str:
    """Return the text body from a message's item list.

    Handles three cases in priority order:
      1. A text item with an optional quoted/referenced message prefix
      2. A voice item with speech-to-text transcription
      3. Empty string if neither is found
    """
    for item in msg.item_list:
        if item.type == MessageItemType.TEXT and item.text_item is not None:
            text = item.text_item.text
            # Prepend quoted message context if present and not a media ref
            ref = item.ref_msg
            if (
                ref is not None
                and ref.message_item is not None
                and not is_media_item(ref.message_item)
            ):
                ref_body = ""
                if ref.message_item.text_item is not None:
                    ref_body = ref.message_item.text_item.text
                title = ref.title
                if title or ref_body:
                    text = f"[引用: {title} | {ref_body}]\n{text}"
            return text

    # Fallback: voice-to-text transcription
    for item in msg.item_list:
        if item.type == MessageItemType.VOICE and item.voice_item is not None and item.voice_item.text:
            return item.voice_item.text

    return ""


def print_qrcode(url: str) -> None:
    """Print a QR code to the terminal using ASCII blocks.

    Requires the optional ``qrcode`` package::

        pip install qrcode
    """
    import sys

    try:
        import qrcode
    except ImportError:
        raise ImportError(
            "print_qrcode() requires the 'qrcode' package.\n"
            "Install it with: pip install qrcode"
        ) from None

    qr = qrcode.QRCode(
        box_size=1,
        border=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Render to a UTF-8 StringIO to avoid Windows GBK encoding issues,
    # then write with fallback.
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    text = buf.getvalue()
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        # Fallback: use ## for dark and spaces for light
        matrix = qr.get_matrix()
        for row in matrix:
            print("".join("##" if cell else "  " for cell in row))
    sys.stdout.flush()
