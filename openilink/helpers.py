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


def print_qrcode(url: str) -> None:
    """Print a QR code to the terminal using ASCII blocks."""
    import io
    import sys
    import qrcode

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
