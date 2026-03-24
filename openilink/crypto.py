"""AES-128-ECB encryption utilities for CDN media."""

from __future__ import annotations

import base64
import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


AES_BLOCK_SIZE = 16


def pkcs7_pad(data: bytes, block_size: int = AES_BLOCK_SIZE) -> bytes:
    """Pad data to a multiple of block_size using PKCS#7."""
    pad = block_size - len(data) % block_size
    return data + bytes([pad] * pad)


def pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS#7 padding."""
    if not data:
        raise ValueError("pkcs7 unpad: empty data")
    pad = data[-1]
    if pad == 0 or pad > AES_BLOCK_SIZE or pad > len(data):
        raise ValueError(f"pkcs7 unpad: invalid padding {pad}")
    if any(b != pad for b in data[-pad:]):
        raise ValueError("pkcs7 unpad: inconsistent padding")
    return data[:-pad]


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-128-ECB and PKCS#7 padding."""
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    padded = pkcs7_pad(plaintext)
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB ciphertext and remove PKCS#7 padding."""
    if len(ciphertext) % AES_BLOCK_SIZE != 0:
        raise ValueError("ciphertext not multiple of block size")
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return pkcs7_unpad(plaintext)


def aes_ecb_padded_size(plaintext_size: int) -> int:
    """Return the ciphertext size for a given plaintext size."""
    return ((plaintext_size + 1 + AES_BLOCK_SIZE - 1) // AES_BLOCK_SIZE) * AES_BLOCK_SIZE


def _is_hex(b: bytes) -> bool:
    try:
        binascii.unhexlify(b)
        return len(b) > 0
    except (ValueError, binascii.Error):
        return False


def _decode_base64_flexible(s: str) -> bytes:
    """Decode base64 with support for standard and URL-safe, with or without padding."""
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        for pad in (True, False):
            try:
                data = s if pad else s.rstrip("=")
                return decoder(data + "=" * (-len(data) % 4) if not pad else data)
            except Exception:
                continue
    raise ValueError(f"invalid base64: {s!r}")


def parse_aes_key(aes_key_base64: str) -> bytes:
    """Decode a base64-encoded AES key.

    Two encodings are seen in the wild:
      - base64(raw 16 bytes) -- images
      - base64(hex string of 16 bytes) -- file / voice / video
    """
    decoded = _decode_base64_flexible(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and _is_hex(decoded):
        return binascii.unhexlify(decoded)
    raise ValueError(
        f"aes_key must decode to 16 raw bytes or 32-char hex, got {len(decoded)} bytes"
    )
