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
    """Print a QR code to the terminal using compact single-char blocks.

    Also saves a PNG image to ``.ilink/qrcode.png`` and attempts to open it,
    which is more reliable in environments with limited terminal width
    (e.g. Claude Code).

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

    # Save as PNG and try to open with system viewer
    _save_and_open_qrcode(qr)

    # Compact terminal rendering: 1 char per module using half-block chars.
    # ▀ (upper half), ▄ (lower half), █ (full), ' ' (empty).
    # Each output row encodes two QR rows, halving the height.
    matrix = qr.get_matrix()
    rows = len(matrix)
    DARK = True
    LIGHT = False

    lines: list[str] = []
    for y in range(0, rows, 2):
        row_top = matrix[y]
        row_bot = matrix[y + 1] if y + 1 < rows else [LIGHT] * len(row_top)
        chars: list[str] = []
        for top, bot in zip(row_top, row_bot):
            if top and bot:
                chars.append("\u2588")      # █  both dark
            elif top and not bot:
                chars.append("\u2580")      # ▀  top dark
            elif not top and bot:
                chars.append("\u2584")      # ▄  bottom dark
            else:
                chars.append(" ")           #    both light
        lines.append("".join(chars))

    text = "\n".join(lines) + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        # Fallback: plain ASCII, 1 char per module
        for row in matrix:
            print("".join("#" if cell else " " for cell in row))
    sys.stdout.flush()


def _save_and_open_qrcode(qr) -> None:
    """Save QR code as PNG to .ilink/qrcode.png and open with system viewer."""
    import subprocess
    import sys
    from pathlib import Path

    qr_dir = Path(".ilink")
    qr_dir.mkdir(exist_ok=True)
    qr_path = qr_dir / "qrcode.png"

    try:
        img = qr.make_image(fill_color="black", back_color="white")
        # make_image may need pillow; scale up for scanning
        img = img.resize((img.size[0] * 10, img.size[1] * 10))
        img.save(str(qr_path))
        print(f"QR code saved to: {qr_path.resolve()}")
    except Exception:
        # Pillow not installed or save failed — skip silently
        return

    # Try to open with system viewer
    try:
        if sys.platform == "win32":
            os.startfile(str(qr_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(qr_path)])
        else:
            subprocess.Popen(["xdg-open", str(qr_path)])
    except Exception:
        pass
