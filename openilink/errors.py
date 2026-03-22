"""Custom exceptions for the openilink SDK."""


class APIError(Exception):
    """Error response from the iLink API."""

    def __init__(self, ret: int = 0, errcode: int = 0, errmsg: str = ""):
        self.ret = ret
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"ilink: api error ret={ret} errcode={errcode} errmsg={errmsg}")

    def is_session_expired(self) -> bool:
        return self.errcode == -14 or self.ret == -14


class HTTPError(Exception):
    """Non-2xx HTTP response from the server."""

    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self.body = body
        super().__init__(f"ilink: http {status_code}: {body.decode(errors='replace')}")


class NoContextTokenError(Exception):
    """No cached context token exists for the target user."""

    def __init__(self):
        super().__init__("ilink: no cached context token; user must send a message first")
