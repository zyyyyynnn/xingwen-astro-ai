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
import { ArtifactPresentationContent } from "./scientific-presentation";
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
  /** Immutable binary read channel, only used by model_artifact content. */
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

function ScientificArtifactContent({
  review,
  presentation,
  title,
  surface,
  onSelectEvidence,
  loadContent,
}: {
  readonly review: ScientificArtifactReview;
  readonly presentation: PublicArtifactPresentation;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  if ("content" in review) {
    const { content, sourceMode } = review;
    if (content.kind === "analysis_report") {
      return (
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <AnalysisReportContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            enhancementOnly
          />
        </>
      );
    }
    if (content.kind === "model_evaluation") {
      return (
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <ModelEvaluationContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            enhancementOnly
          />
        </>
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
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <ModelArtifactContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            loadContent={loadContent}
            enhancementOnly
          />
        </>
      );
    }
    if (content.kind === "visualization") {
      return (
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <VisualizationContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            versionNumber={review.versionNumber}
            loadContent={loadContent}
            enhancementOnly
          />
        </>
      );
    }
    if (content.kind === "spectrum") {
      return (
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <SpectrumContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            enhancementOnly
          />
        </>
      );
    }
    if (content.kind === "light_curve") {
      return (
        <>
          <ArtifactPresentationContent
            presentation={presentation}
            title={title}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
            showHeader={false}
          />
          <LightCurveContent
            content={content}
            title={title}
            sourceMode={sourceMode}
            surface={surface}
            enhancementOnly
          />
        </>
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
      showHeader={false}
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
