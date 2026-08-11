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
} from "./view-model";
import type {
  ArtifactVersionMetadata,
  Evidence,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
} from "@xingwen/domain";

export interface ResearchAdapter {
  toProjectViewModel(project: ResearchProject): ProjectViewModel;
  toContractDraftViewModel(
    draft: ResearchContractDraft,
  ): ResearchContractDraftViewModel;
  toContractViewModel(contract: ResearchContract): ResearchContractViewModel;
  toRunViewModel(run: ResearchRun): ResearchRunViewModel;
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
  toArtifactViewModel,
  toArtifactVersionViewModel,
  toEvidenceViewModel,
  toActivityPresentationEvent,
  toApplicationCommand,
  toPublicApplicationError,
});
