import type {
  ContentHash,
  DomainEntityId,
  PublicArtifactPresentation,
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
import {
  ArtifactPresentationContent,
  type PresentationRevisionIntent,
} from "./scientific-presentation";
import {
  ModelArtifactContent,
  ModelEvaluationContent,
} from "./scientific-content/model-evaluation-content";
import { SpectrumContent } from "./scientific-content/spectrum-content";
import type { ScientificContentSurface } from "./scientific-content/shared";
import { VisualizationContent } from "./scientific-content/visualization-content";

export type ScientificArtifactSurface = ScientificContentSurface;

type ScientificArtifactReview =
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | DomainScientificArtifactReview;

export interface ScientificArtifactRendererProps {
  readonly review: ScientificArtifactReview;
  readonly presentation: PublicArtifactPresentation;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly onRequestRevision?: (intent: PresentationRevisionIntent) => void;
  /** Immutable binary read channel, only used by model_artifact content. */
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

function ScientificArtifactContent({
  review,
  presentation,
  title,
  surface,
  onSelectEvidence,
  onRequestRevision,
  loadContent,
}: {
  readonly review: ScientificArtifactReview;
  readonly presentation: PublicArtifactPresentation;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly onRequestRevision?: (intent: PresentationRevisionIntent) => void;
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
  if (review.kind === "graph") {
    return (
      <GraphContent
        review={review}
        presentation={presentation}
        title={title}
        surface={surface}
        onSelectEvidence={onSelectEvidence}
      />
    );
  }
  return (
    <ArtifactPresentationContent
      presentation={presentation}
      title={title}
      surface={surface}
      onSelectEvidence={onSelectEvidence}
      onRequestRevision={onRequestRevision}
      showHeader={false}
    />
  );
}

export function ScientificArtifactRenderer({
  onSelectEvidence,
  onRequestRevision,
  ...props
}: ScientificArtifactRendererProps) {
  const evidenceIds =
    "content" in props.review
      ? props.review.content.evidenceIds
      : "evidenceIds" in props.review
        ? props.review.evidenceIds
        : [];
  const hasInlineEvidence =
    props.presentation.kind === "literature_claims" ||
    props.presentation.kind === "literature_relations";
  return (
    <>
      <ScientificArtifactContent
        {...props}
        onSelectEvidence={onSelectEvidence}
        onRequestRevision={onRequestRevision}
      />
      {hasInlineEvidence ? null : (
        <EvidenceLinks
          evidenceIds={evidenceIds}
          label={`${props.title}的证据`}
          onSelectEvidence={onSelectEvidence}
        />
      )}
    </>
  );
}
