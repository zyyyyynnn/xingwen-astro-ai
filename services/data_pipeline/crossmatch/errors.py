"""Stable C-08 domain errors."""

from __future__ import annotations


class CrossmatchError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CrossmatchCapacityError(CrossmatchError):
    pass
