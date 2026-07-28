/**
 * Artifact content dispatch for the central Research Canvas.
 *
 * Routes the selected Artifact to its kind-specific review surface: a
 * `paper_collection` version renders the A-05 Paper Acquisition Workspace
 * (reading rich content through its dedicated repository port); every other
 * kind keeps the existing generic identity/provenance panel.
 */

import type { PaperAcquisitionRepository } from "@xingwen/data-access";
import type {
  ArtifactVersionMetadata,
  Evidence,
  PaperCandidateReview,
  ResearchArtifact,
} from "@xingwen/domain";

import { PaperAcquisitionWorkspace } from "../features/paper-acquisition/paper-acquisition-workspace";

export interface ArtifactCanvasProps {
  readonly artifact: ResearchArtifact;
  readonly version: ArtifactVersionMetadata;
  readonly paperAcquisition: PaperAcquisitionRepository;
  readonly executionMode: string | null;
  readonly ready: boolean;
  readonly disabled: boolean;
  readonly selectedCandidateId: string | null;
  readonly onSelectCandidate: (candidate: PaperCandidateReview) => void;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

export function ArtifactCanvas({
  artifact,
  version,
  paperAcquisition,
  executionMode,
  ready,
  disabled,
  selectedCandidateId,
  onSelectCandidate,
  onSelectEvidence,
}: ArtifactCanvasProps) {
  if (artifact.kind === "paper_collection") {
    return (
      <PaperAcquisitionWorkspace
        artifactVersionId={version.id}
        repository={paperAcquisition}
        executionMode={executionMode}
        ready={ready}
        disabled={disabled}
        selectedCandidateId={selectedCandidateId}
        onSelectCandidate={onSelectCandidate}
        onSelectEvidence={onSelectEvidence}
      />
    );
  }
  return (
    <section className="work-panel" aria-labelledby="artifact-title">
      <h2 id="artifact-title">{artifact.title}</h2>
      <p>
        {artifact.kind} / v{version.versionNumber} / {version.sourceMode}
      </p>
      <p>{version.contentHash}</p>
    </section>
  );
}
