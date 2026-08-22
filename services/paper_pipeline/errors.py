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
