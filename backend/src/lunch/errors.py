class DomainError(Exception):
    """Business-rule violation; mapped to an HTTP error response."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status_code = 404


class Unauthorized(DomainError):
    status_code = 401


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    status_code = 409
