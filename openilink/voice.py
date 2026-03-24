"""Voice message utilities — SILK decoding and WAV building."""

from __future__ import annotations

import struct
from typing import Callable, Optional

from .types import VoiceItem

# Type alias for a pluggable SILK decoder function.
# Signature: (silk_data: bytes, sample_rate: int) -> pcm: bytes
SILKDecoder = Callable[[bytes, int], bytes]

DEFAULT_VOICE_SAMPLE_RATE = 24000


def build_wav(
    pcm: bytes,
    sample_rate: int = DEFAULT_VOICE_SAMPLE_RATE,
    num_channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """Wrap raw PCM data (signed 16-bit LE) in a WAV container."""
    data_size = len(pcm)
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8

    header = struct.pack(
        "<4sI4s"       # RIFF header
        "4sIHHIIHH"    # fmt subchunk
        "4sI",         # data subchunk header
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,                         # subchunk size
        1,                          # audio format (PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm


def download_voice(
    client,
    voice: VoiceItem,
    silk_decoder: Optional[SILKDecoder] = None,
) -> bytes:
    """Download a voice message from CDN, decrypt, decode SILK, return WAV.

    Requires a SILK decoder function. Example using the ``silk`` package::

        from silk import decode as silk_decode
        wav = download_voice(client, voice_item, silk_decoder=silk_decode)
    """
    if silk_decoder is None:
        raise ValueError("no SILK decoder provided; pass a silk_decoder function")
    if voice is None or voice.media is None:
        raise ValueError("voice item or media is nil")

    # 1. Download and decrypt
    data = client.download_file(voice.media.encrypt_query_param, voice.media.aes_key)

    # 2. Determine sample rate
    sample_rate = voice.sample_rate if voice.sample_rate > 0 else DEFAULT_VOICE_SAMPLE_RATE

    # 3. Decode SILK -> PCM
    pcm = silk_decoder(data, sample_rate)

    # 4. Wrap in WAV
    return build_wav(pcm, sample_rate, 1, 16)
