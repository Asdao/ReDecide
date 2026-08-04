"""Typed integration errors converted to the shared API error envelope."""

from backend.app.contracts import APIErrorCode


class IntegrationError(Exception):
    def __init__(
        self,
        *,
        code: APIErrorCode,
        message: str,
        status_code: int,
        retryable: bool = False,
        decision_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.decision_id = decision_id
