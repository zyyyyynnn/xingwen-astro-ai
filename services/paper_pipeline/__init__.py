"""D-02 PaperCollection and D-03 PaperSummary pipelines."""

from .pipeline import PaperCollectionPipeline
from .summary import PaperSummaryPipeline

__all__ = ["PaperCollectionPipeline", "PaperSummaryPipeline"]
