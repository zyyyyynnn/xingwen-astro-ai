import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";
import type { ScientificSkillId } from "./enums";

export type RunStepStatus =
  | "pending"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped";

export interface RunStepSnapshot {
  readonly id: DomainEntityId;
  readonly runId: DomainEntityId;
  readonly position: number;
  readonly key: DomainEntityId;
  readonly label: string;
  readonly phase: string;
  readonly taskId: DomainEntityId | null;
  readonly skillId: ScientificSkillId | null;
  readonly dependsOnStepKeys: readonly DomainEntityId[];
  readonly status: RunStepStatus;
  readonly progress: number;
  readonly publicMessage: string;
  readonly startedAt: UtcIsoTimestamp | null;
  readonly finishedAt: UtcIsoTimestamp | null;
  readonly failureCode: string | null;
}
