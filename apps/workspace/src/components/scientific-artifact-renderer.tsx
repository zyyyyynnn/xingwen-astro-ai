import type {
  DomainEntityId,
  ScientificArtifactReview as DomainScientificArtifactReview,
} from "@xingwen/domain";
import type {
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
} from "@xingwen/research-adapter";

import { EvidenceLinks } from "./evidence-links";
import { GraphContent } from "./scientific-content/graph-content";
import { LightCurveContent } from "./scientific-content/light-curve-content";
import { LiteratureContent } from "./scientific-content/literature-content";
import { PaperCollectionContent } from "./scientific-content/paper-collection-content";
import type { PaperCollectionReviewViewModel } from "./scientific-content/paper-collection-content";
import { SpectrumContent } from "./scientific-content/spectrum-content";
import type { ScientificContentSurface } from "./scientific-content/shared";

export type ScientificArtifactSurface = ScientificContentSurface;

type ScientificArtifactReview =
  | PaperCollectionReviewViewModel
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | DomainScientificArtifactReview;

export interface ScientificArtifactRendererProps {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}

function ScientificArtifactContent({
  review,
  title,
  surface,
}: {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
}) {
  if ("content" in review) {
    const { content, sourceMode } = review;
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
  return <LiteratureContent review={review} title={title} surface={surface} />;
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
      <ScientificArtifactContent {...props} />
      <EvidenceLinks
        evidenceIds={evidenceIds}
        label={`${props.title}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </>
  );
}
