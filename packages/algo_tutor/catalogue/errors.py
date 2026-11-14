"""Errors the catalogue services raise, each mapping to one API error (SPEC §18.1)."""


class CatalogueError(Exception):
    """Base class. `code` is the API error code; `status` its HTTP status."""

    code = "VALIDATION"
    status = 422

    def __init__(self, message: str) -> None:
        """Store *message* for the API error body."""
        super().__init__(message)
        self.message = message


class InvalidInput(CatalogueError):
    """The request data is invalid (HTTP 422)."""

    code = "VALIDATION"
    status = 422


class NotFound(CatalogueError):
    """The requested item does not exist (HTTP 404)."""

    code = "NOT_FOUND"
    status = 404


class Conflict(CatalogueError):
    """The request clashes with what exists: a taken name, setup already done, a read-only list."""

    code = "CONFLICT"
    status = 409
