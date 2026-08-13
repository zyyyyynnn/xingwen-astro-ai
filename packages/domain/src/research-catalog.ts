import type { ArtifactKind, ScientificSkillId } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type { CaseKey } from "./value-types";

export interface ResearchCatalogOption<Value extends string = string> {
  readonly value: Value;
  readonly label: string;
  readonly description: string;
  readonly group: "common" | "advanced" | null;
}

export interface ResearchPlanningCatalog {
  readonly projectId: DomainEntityId;
  readonly caseKey: CaseKey;
  readonly targetObjects: readonly ResearchCatalogOption<DomainEntityId>[];
  readonly requestedFields: readonly ResearchCatalogOption<DomainEntityId>[];
  readonly allowedSources: readonly ResearchCatalogOption<DomainEntityId>[];
  readonly scientificSkills: readonly ResearchCatalogOption<ScientificSkillId>[];
  readonly outputRequirements: readonly ResearchCatalogOption<ArtifactKind>[];
}
