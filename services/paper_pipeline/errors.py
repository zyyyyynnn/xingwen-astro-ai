from __future__ import annotations

from typing import Literal


class PaperSearchExecutionError(RuntimeError):
    """Domain exception for paper search execution failures and rejections."""

    def __init__(
        self,
        *,
        code: str,
        public_message: str,
        retryable: bool,
        producer_status: Literal["failed", "rejected"],
    ) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = retryable
        self.producer_status = producer_status


class LiteratureAdmissionExecutionError(RuntimeError):
    """Retryable rejection from the production literature admission boundary."""

    def __init__(self, *, code: str, public_message: str) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = True


class LiteratureClaimExecutionError(RuntimeError):
    """Final, non-retryable Claims chunk-contract failure after bounded recovery."""

    def __init__(self, *, code: str, public_message: str) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = False


class PaperSummaryExecutionError(RuntimeError):
    """Typed PaperSummary execution failure with explicit retry semantics."""

    def __init__(self, *, code: str, public_message: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = retryable


class LiteratureRelationLocalError(RuntimeError):
    """Non-retryable unexpected local validation failure in the Relation path."""

    def __init__(self, *, code: str, public_message: str) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = False
