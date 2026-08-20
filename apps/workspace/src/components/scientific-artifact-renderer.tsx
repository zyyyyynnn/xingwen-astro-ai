import type {
  ContentHash,
  DomainEntityId,
  ScientificArtifactReview as DomainScientificArtifactReview,
} from "@xingwen/domain";
import type {
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
} from "@xingwen/research-adapter";

import { EvidenceLinks } from "./evidence-links";
import { AnalysisReportContent } from "./scientific-content/analysis-report-content";
import { GraphContent } from "./scientific-content/graph-content";
import { LightCurveContent } from "./scientific-content/light-curve-content";
import { LiteratureContent } from "./scientific-content/literature-content";
import {
  ModelArtifactContent,
  ModelEvaluationContent,
} from "./scientific-content/model-evaluation-content";
import { PaperCollectionContent } from "./scientific-content/paper-collection-content";
import type { PaperCollectionReviewViewModel } from "./scientific-content/paper-collection-content";
import { SpectrumContent } from "./scientific-content/spectrum-content";
import type { ScientificContentSurface } from "./scientific-content/shared";
import { VisualizationContent } from "./scientific-content/visualization-content";

export type ScientificArtifactSurface = ScientificContentSurface;

type ScientificArtifactReview =
  | PaperCollectionReviewViewModel
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | DomainScientificArtifactReview;

export interface ScientificArtifactRendererProps {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  /** Immutable binary read channel, only used by model_artifact content. */
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

function ScientificArtifactContent({
  review,
  title,
  surface,
  onSelectEvidence,
  loadContent,
}: {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  if ("content" in review) {
    const { content, sourceMode } = review;
    if (content.kind === "analysis_report") {
      return (
        <AnalysisReportContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      );
    }
    if (content.kind === "model_evaluation") {
      return (
        <ModelEvaluationContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      );
    }
    if (content.kind === "model_artifact") {
      if (!loadContent) {
        return (
          <p className="scientific-artifact__empty">
            当前界面未接入模型二进制读取通道。
          </p>
        );
      }
      return (
        <ModelArtifactContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
          loadContent={loadContent}
        />
      );
    }
    if (content.kind === "visualization") {
      return (
        <VisualizationContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
          versionNumber={review.versionNumber}
          loadContent={loadContent}
        />
      );
    }
    if (content.kind === "spectrum") {
      return (
        <SpectrumContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
        />
      );
    }
    if (content.kind === "light_curve") {
      return (
        <LightCurveContent
          content={content}
          title={title}
          sourceMode={sourceMode}
          surface={surface}
        />
      );
    }
    return null;
  }
  if (review.kind === "paper_collection") {
    return (
      <PaperCollectionContent review={review} title={title} surface={surface} />
    );
  }
  if (review.kind === "graph") {
    return <GraphContent review={review} title={title} surface={surface} />;
  }
  return (
    <LiteratureContent
      review={review}
      title={title}
      surface={surface}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

export function ScientificArtifactRenderer({
  onSelectEvidence,
  ...props
}: ScientificArtifactRendererProps) {
  const evidenceIds =
    "content" in props.review
      ? props.review.content.evidenceIds
      : "evidenceIds" in props.review
        ? props.review.evidenceIds
        : [];
  return (
    <>
      <ScientificArtifactContent
        {...props}
        onSelectEvidence={onSelectEvidence}
      />
      <EvidenceLinks
        evidenceIds={evidenceIds}
        label={`${props.title}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </>
  );
}
