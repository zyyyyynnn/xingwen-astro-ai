"""Data-quality evaluation and process-local Publisher handoff."""

from .evaluator import evaluate_data_quality


def admit_data_artifact_quality(*args, **kwargs):
    from .admission import admit_data_artifact_quality as _admit

    return _admit(*args, **kwargs)


def build_data_quality_publication_validator(*args, **kwargs):
    from .admission import build_data_quality_publication_validator as _build

    return _build(*args, **kwargs)

__all__ = [
    "admit_data_artifact_quality",
    "build_data_quality_publication_validator",
    "evaluate_data_quality",
]
