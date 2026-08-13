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
} from "./view-model";
import type {
  ArtifactVersionMetadata,
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
  toActivityPresentationEvent,
  toApplicationCommand,
  toPublicApplicationError,
});
