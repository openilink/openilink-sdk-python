"""HTTP abstraction layer — mirrors Go's HTTPDoer interface.

Implement the :class:`HTTPDoer` protocol to plug in a custom transport
(e.g. httpx, aiohttp adapter, or a mock for testing).
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable
from urllib.request import Request, urlopen
from urllib.error import HTTPError as _URLHTTPError


@dataclass
class Response:
    """Minimal HTTP response returned by :class:`HTTPDoer`."""
    status_code: int
    content: bytes


@runtime_checkable
class HTTPDoer(Protocol):
    """Interface for executing HTTP requests.

    This mirrors Go's ``HTTPDoer`` interface, making it easy to swap in
    a custom transport layer or a mock for unit testing::

        class MockHTTPDoer:
            def do(self, method, url, *, headers=None, body=None, timeout=15):
                return Response(status_code=200, content=b'{"ret":0}')

        client = Client(http_doer=MockHTTPDoer())
    """

    def do(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: float = 15,
    ) -> Response:
        """Execute an HTTP request and return the response."""
        ...


class DefaultHTTPDoer:
    """Default :class:`HTTPDoer` using only the Python standard library.

    Uses :func:`urllib.request.urlopen` under the hood — zero external
    dependencies.
    """

    def __init__(self) -> None:
        self._ssl_ctx = ssl.create_default_context()

    def do(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: float = 15,
    ) -> Response:
        req = Request(url, data=body, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)

        try:
            with urlopen(req, timeout=timeout, context=self._ssl_ctx) as resp:
                return Response(status_code=resp.status, content=resp.read())
        except _URLHTTPError as e:
            return Response(status_code=e.code, content=e.read())
