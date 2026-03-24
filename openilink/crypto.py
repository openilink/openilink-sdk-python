"""AES-128-ECB encryption utilities for CDN media."""

from __future__ import annotations

import base64


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty data")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError(f"invalid PKCS#7 padding: {pad_len}")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("bad PKCS#7 padding")
    return data[:-pad_len]


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-128-ECB and PKCS#7 padding."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padded = _pkcs7_pad(plaintext)
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB ciphertext and remove PKCS#7 padding."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()
    return _pkcs7_unpad(padded)


def aes_ecb_padded_size(plaintext_size: int) -> int:
    """Return the ciphertext size for a given plaintext size."""
    return plaintext_size + (16 - plaintext_size % 16)


def _is_hex(s: str) -> bool:
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False


def parse_aes_key(aes_key_base64: str) -> bytes:
    """Decode a base64-encoded AES key.

    Supports two encodings used by the iLink API:
      - base64(raw 16 bytes) — images
      - base64(hex string of 16 bytes) — file/voice/video
    """
    raw = base64.b64decode(aes_key_base64)
    # If the decoded bytes are a 32-char hex string, decode the hex
    if len(raw) == 32 and _is_hex(raw.decode("ascii", errors="replace")):
        return bytes.fromhex(raw.decode("ascii"))
    if len(raw) == 16:
        return raw
    raise ValueError(f"unexpected AES key length: {len(raw)} bytes")
