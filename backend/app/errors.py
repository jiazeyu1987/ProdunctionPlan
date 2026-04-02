from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def not_found(code: str, message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(code=code, message=message, status_code=404, details=details)


def bad_request(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> AppError:
    return AppError(code=code, message=message, status_code=400, details=details)


def unauthorized(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> AppError:
    return AppError(code=code, message=message, status_code=401, details=details)


def forbidden(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> AppError:
    return AppError(code=code, message=message, status_code=403, details=details)


def server_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> AppError:
    return AppError(code=code, message=message, status_code=500, details=details)
