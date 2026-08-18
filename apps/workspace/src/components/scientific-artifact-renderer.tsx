import type { DomainEntityId } from "@xingwen/domain";
import type {
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
} from "@xingwen/research-adapter";

import { GraphContent } from "./scientific-content/graph-content";
import { LiteratureContent } from "./scientific-content/literature-content";
import { PaperCollectionContent } from "./scientific-content/paper-collection-content";
import type { PaperCollectionReviewViewModel } from "./scientific-content/paper-collection-content";
import type { ScientificContentSurface } from "./scientific-content/shared";

export type ScientificArtifactSurface = ScientificContentSurface;

type ScientificArtifactReview =
  | PaperCollectionReviewViewModel
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel;

export interface ScientificArtifactRendererProps {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}

function ScientificArtifactContent({
  review,
  title,
  surface,
  onSelectEvidence,
}: {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
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

export function ScientificArtifactRenderer(
  props: ScientificArtifactRendererProps,
) {
  return <ScientificArtifactContent {...props} />;
}
