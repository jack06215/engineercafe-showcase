"""Error responses (SPEC §18.1): always `{"error": {"code", "message"}}`."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from packages.algo_tutor.api.schemas import ErrorBody, ErrorDetail
from packages.algo_tutor.catalogue.errors import CatalogueError
from packages.algo_tutor.domain.enums import TutorErrorKind


class ApiError(Exception):
    """An error with a SPEC §18.1 code. Raise it from any route."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        kind: TutorErrorKind | None = None,
    ) -> None:
        """Store the HTTP *status*, error *code* and *message* for the response."""
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.kind = kind


def not_found(what: str) -> ApiError:
    """Return a 404 NOT_FOUND error for *what*."""
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def stale(what: str) -> ApiError:
    """Return a 409 STALE error for *what*."""
    return ApiError(409, "STALE", f"{what} changed elsewhere; reload it")


def hidden_assessment() -> ApiError:
    """Return the 403 error for data locked during the hidden assessment."""
    return ApiError(403, "HIDDEN_ASSESSMENT", "Locked until you finish the assessment")


def error_response(
    status: int, code: str, message: str, kind: TutorErrorKind | None = None
) -> JSONResponse:
    """Build the JSON response for an API error."""
    body = ErrorBody(error=ErrorDetail(code=code, message=message, kind=kind))
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json", exclude_none=True)
    )


def _first_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request"
    first = errors[0]
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = str(first.get("msg", "invalid"))
    return f"{where}: {message}" if where else message


_HTTP_CODES = {404: "NOT_FOUND", 405: "NOT_FOUND", 422: "VALIDATION"}


def install_error_handlers(app: FastAPI) -> None:
    """Route every error through the SPEC §18.1 shape."""

    async def on_api_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(exc.status, exc.code, exc.message, exc.kind)

    async def on_validation(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return error_response(422, "VALIDATION", _first_validation_message(exc))

    async def on_catalogue(_: Request, exc: Exception) -> JSONResponse:
        # The catalogue services' own errors carry their code and status.
        assert isinstance(exc, CatalogueError)
        return error_response(exc.status, exc.code, exc.message)

    async def on_http(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, HTTPException)
        code = _HTTP_CODES.get(exc.status_code, "ERROR")
        return error_response(exc.status_code, code, str(exc.detail))

    app.add_exception_handler(ApiError, on_api_error)
    app.add_exception_handler(RequestValidationError, on_validation)
    app.add_exception_handler(CatalogueError, on_catalogue)
    app.add_exception_handler(HTTPException, on_http)
