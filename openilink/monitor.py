"""Long-poll message monitor for the iLink Bot API."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable, Optional

from .errors import APIError

logger = logging.getLogger("openilink.monitor")

if TYPE_CHECKING:
    from .client import Client
    from .types import WeixinMessage

INITIAL_BACKOFF = 2    # seconds
MAX_BACKOFF = 60       # seconds


class MonitorOptions:
    """Configures the long-poll monitor loop."""

    def __init__(
        self,
        initial_buf: str = "",
        on_buf_update: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_session_expired: Optional[Callable[[], None]] = None,
    ):
        self.initial_buf = initial_buf
        self.on_buf_update = on_buf_update
        self.on_error = on_error or (lambda e: None)
        self.on_session_expired = on_session_expired


def _safe_callback(fn: Callable, *args: object) -> None:
    """Invoke a callback, catching and logging any exception it raises."""
    try:
        fn(*args)
    except Exception as exc:
        logger.error("callback %s raised: %s", getattr(fn, "__name__", fn), exc)


def monitor(
    client: Client,
    handler: Callable[[WeixinMessage], None],
    opts: Optional[MonitorOptions] = None,
) -> None:
    """Run a long-poll loop, invoking handler for each inbound message.

    Blocks until client.stop() is called. Handles retries/backoff automatically.
    Context tokens are cached automatically for use with client.push().
    """
    if opts is None:
        opts = MonitorOptions()

    buf = opts.initial_buf
    backoff = INITIAL_BACKOFF

    while not client.stopped:
        try:
            resp = client.get_updates(buf)
        except Exception as exc:
            if client.stopped:
                return
            _safe_callback(opts.on_error, Exception(f"getUpdates: {exc}"))
            _sleep_or_stop(client, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        # API-level error
        if resp.ret != 0 or resp.errcode != 0:
            api_err = APIError(ret=resp.ret, errcode=resp.errcode, errmsg=resp.errmsg)

            if api_err.is_session_expired():
                if opts.on_session_expired:
                    _safe_callback(opts.on_session_expired)
                _safe_callback(opts.on_error, api_err)
                _sleep_or_stop(client, 300)  # 5 minutes
                continue

            _safe_callback(opts.on_error, Exception(f"getUpdates: {api_err}"))
            _sleep_or_stop(client, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        # Success: reset backoff
        backoff = INITIAL_BACKOFF

        # Update sync cursor
        if resp.get_updates_buf:
            buf = resp.get_updates_buf
            if opts.on_buf_update:
                _safe_callback(opts.on_buf_update, buf)

        # Dispatch messages
        for msg in resp.msgs:
            if msg.context_token and msg.from_user_id:
                client.set_context_token(msg.from_user_id, msg.context_token)
            _safe_callback(handler, msg)


def _sleep_or_stop(client: Client, seconds: float) -> None:
    """Sleep in small increments so we can respond to stop quickly."""
    end = time.monotonic() + seconds
    while time.monotonic() < end and not client.stopped:
        time.sleep(min(0.5, end - time.monotonic()))
