import type {
  ArtifactVersionMetadata,
  DataArtifactReview,
  Evidence,
  GraphArtifactReview,
  LiteratureArtifactReview,
  PaperAcquisitionReview,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  ResearchThreadEntry,
  ResearchTurn,
  RunCheckpoint,
  RunEvent,
  RunStepSnapshot,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  DataArtifactReviewViewModel,
  EvidenceViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
  ProjectViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  ResearchTurnViewModel,
  RunCheckpointViewModel,
  RunStepViewModel,
} from "./view-model";

import {
  mergeActivityPresentationEvents,
  toActivityPresentationEvent,
  type ActivityPresentationEvent,
} from "./activity";
import {
  toApplicationCommand,
  type ApplicationCommand,
  type ApplicationIntent,
  type CommandContext,
} from "./commands";
import { toPublicApplicationError } from "./public-error";
import {
  toArtifactVersionMetadataViewModel,
  toArtifactViewModel,
  toContractDraftViewModel,
  toContractViewModel,
  toDataArtifactViewModel,
  toEvidenceViewModel,
  toGraphArtifactViewModel,
  toLiteratureArtifactViewModel,
  toPaperAcquisitionViewModel,
  toProjectViewModel,
  toResearchThreadEntryViewModel,
  toResearchTurnViewModel,
  toRunCheckpointViewModel,
  toRunStepViewModel,
  toRunViewModel,
} from "./view-model-mappers";
import type { PublicApplicationError } from "./public-error";

export interface ResearchAdapter {
  toProjectViewModel(project: ResearchProject): ProjectViewModel;
  toContractDraftViewModel(
    draft: ResearchContractDraft,
  ): ResearchContractDraftViewModel;
  toContractViewModel(contract: ResearchContract): ResearchContractViewModel;
  toRunViewModel(run: ResearchRun): ResearchRunViewModel;
  toResearchThreadEntryViewModel(
    entry: ResearchThreadEntry,
  ): ResearchThreadEntryViewModel;
  toResearchTurnViewModel(turn: ResearchTurn): ResearchTurnViewModel;
  toRunStepViewModel(step: RunStepSnapshot): RunStepViewModel;
  toRunCheckpointViewModel(checkpoint: RunCheckpoint): RunCheckpointViewModel;
  toArtifactViewModel(artifact: ResearchArtifact): ResearchArtifactViewModel;
  toArtifactVersionViewModel(
    version: ArtifactVersionMetadata,
  ): ArtifactVersionMetadataViewModel;
  toEvidenceViewModel(evidence: Evidence): EvidenceViewModel;
  toDataArtifactViewModel(
    review: DataArtifactReview,
  ): DataArtifactReviewViewModel;
  toPaperAcquisitionViewModel(
    review: PaperAcquisitionReview,
  ): PaperAcquisitionReviewViewModel;
  toLiteratureArtifactViewModel(
    review: LiteratureArtifactReview,
  ): LiteratureArtifactReviewViewModel;
  toGraphArtifactViewModel(
    review: GraphArtifactReview,
  ): GraphArtifactReviewViewModel;
  toActivityPresentationEvent(event: RunEvent): ActivityPresentationEvent;
  mergeActivityPresentationEvents(
    current: readonly ActivityPresentationEvent[],
    incoming: readonly ActivityPresentationEvent[],
  ): readonly ActivityPresentationEvent[];
  toApplicationCommand(
    intent: ApplicationIntent,
    context: CommandContext,
  ): ApplicationCommand;
  toPublicApplicationError(error: unknown): PublicApplicationError;
}

export const researchAdapter: ResearchAdapter = Object.freeze({
  toProjectViewModel,
  toContractDraftViewModel,
  toContractViewModel,
  toRunViewModel,
  toResearchThreadEntryViewModel,
  toResearchTurnViewModel,
  toRunCheckpointViewModel,
  toRunStepViewModel,
  toArtifactViewModel,
  toArtifactVersionViewModel: toArtifactVersionMetadataViewModel,
  toEvidenceViewModel,
  toDataArtifactViewModel,
  toPaperAcquisitionViewModel,
  toLiteratureArtifactViewModel,
  toGraphArtifactViewModel,
  toActivityPresentationEvent,
  mergeActivityPresentationEvents,
  toApplicationCommand,
  toPublicApplicationError,
});
