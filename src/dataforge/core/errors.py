"""Domain error types and a consistent error envelope.

All inter-service and API errors flow through these types so the gateway can
emit a single, typed error contract regardless of which module raised it.
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Stable error envelope returned to API clients."""

    error: str
    detail: str
    correlation_id: str | None = None


class DataForgeError(Exception):
    """Base class for all domain errors.

    Attributes:
        code: short machine-readable error code.
        detail: human-readable description.
        status_code: HTTP status to map to at the API boundary.
    """

    code: str = "internal_error"
    status_code: int = 500

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code


class NotFoundError(DataForgeError):
    code = "not_found"
    status_code = 404


class ValidationError(DataForgeError):
    code = "validation_error"
    status_code = 422


class ConflictError(DataForgeError):
    code = "conflict"
    status_code = 409


class DependencyError(DataForgeError):
    """A required downstream dependency (db, queue, vector store) failed."""

    code = "dependency_error"
    status_code = 503
