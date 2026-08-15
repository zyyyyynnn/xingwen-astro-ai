import type { RunEvent } from "@xingwen/domain";

import { toActivityPresentationEvent } from "./activity";
import {
  toApplicationCommand,
  type ApplicationCommand,
  type ApplicationIntent,
  type CommandContext,
} from "./commands";
import { toPublicApplicationError } from "./public-error";
import {
  toArtifactVersionViewModel,
  toArtifactViewModel,
  toContractDraftViewModel,
  toContractViewModel,
  toEvidenceViewModel,
  toProjectViewModel,
  toRunViewModel,
  toResearchThreadEntryViewModel,
  toResearchTurnViewModel,
  toRunStepViewModel,
  toDataArtifactViewModel,
  toGraphArtifactViewModel,
  toLiteratureArtifactViewModel,
  toPaperAcquisitionViewModel,
} from "./view-model-mappers";
import type { ActivityPresentationEvent } from "./activity";
import type { PublicApplicationError } from "./public-error";
import type {
  ArtifactVersionMetadataViewModel,
  EvidenceViewModel,
  ProjectViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  ResearchTurnViewModel,
  RunStepViewModel,
  DataArtifactReviewViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
} from "./view-model";
import type {
  ArtifactVersionMetadata,
  DataArtifactReview,
  GraphArtifactReview,
  LiteratureArtifactReview,
  PaperAcquisitionReview,
  Evidence,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  ResearchThreadEntry,
  ResearchTurn,
  RunStepSnapshot,
} from "@xingwen/domain";

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
  toRunStepViewModel,
  toArtifactViewModel,
  toArtifactVersionViewModel,
  toEvidenceViewModel,
  toDataArtifactViewModel,
  toPaperAcquisitionViewModel,
  toLiteratureArtifactViewModel,
  toGraphArtifactViewModel,
  toActivityPresentationEvent,
  toApplicationCommand,
  toPublicApplicationError,
});
