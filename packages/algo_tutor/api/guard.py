"""The local-only guard (SPEC §15).

The server binds to 127.0.0.1, and every request must also:

- carry a `Host` of `127.0.0.1:<port>` or `localhost:<port>` (blocks DNS
  rebinding: a hostile page on another name can't reach us through the
  browser);
- when it has an `Origin`, come from the API's own origin or Vite's dev origin;
- for writes, be `application/json`, body or not (blocks cross-site form
  posts and other "simple" requests, which a browser sends without a
  preflight).

A request that fails gets 403 `NOT_LOCAL`.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from packages.algo_tutor.api.errors import error_response

VITE_DEV_PORT = 5173
_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def allowed_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def allowed_origins(port: int) -> frozenset[str]:
    return frozenset(
        f"http://{host}:{p}"
        for host in ("127.0.0.1", "localhost")
        for p in (port, VITE_DEV_PORT)
    )


def refusal(method: str, headers: dict[str, str], port: int) -> str | None:
    """Why the guard refuses a request, or None to let it through.

    `headers` has lower-case names. Split out so it's testable without HTTP.
    """
    host = headers.get("host", "")
    if host not in allowed_hosts(port):
        return f"Host {host!r} is not this machine"
    origin = headers.get("origin")
    if origin is not None and origin not in allowed_origins(port):
        return f"Origin {origin!r} is not allowed"
    if method in _WRITES:
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return "Writes must be application/json"
    return None


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, port: int) -> None:
        super().__init__(app)
        self.port = port

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        headers = {k.lower(): v for k, v in request.headers.items()}
        reason = refusal(request.method, headers, self.port)
        if reason is not None:
            return error_response(403, "NOT_LOCAL", reason)
        return await call_next(request)
