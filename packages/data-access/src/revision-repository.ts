import type {
  ConfirmRevisionPlanRequest,
  CreateRevisionPlanRequest,
  CreateUserFeedbackRequest,
  RevisionPlan as RevisionPlanDto,
  UserFeedback as UserFeedbackDto,
} from "@xingwen/contracts";
import {
  asEntityId,
  type ResearchRun,
  type RevisionPlan,
  type UserFeedback,
} from "@xingwen/domain";

import { FixtureSemanticError } from "./errors";
import { HttpClient, seg, validateAndMap } from "./http-client";
import { mapResearchRun } from "./mapping";
import type { RevisionRepository } from "./ports";

function mapFeedback(dto: UserFeedbackDto): UserFeedback {
  return {
    id: asEntityId(dto.id),
    projectId: asEntityId(dto.project_id),
    artifactId: asEntityId(dto.artifact_id),
    baselineArtifactVersionId: asEntityId(dto.baseline_artifact_version_id),
    baselineVersionNumber: dto.baseline_version_number,
    baselineContentHash: dto.baseline_content_hash,
    targetType: dto.target_type,
    targetId: asEntityId(dto.target_id),
    targetLocator: dto.target_locator,
    category: dto.category,
    summary: dto.summary,
    requestedChange: dto.requested_change,
    createdAt: dto.created_at,
  };
}

function mapPlan(dto: RevisionPlanDto): RevisionPlan {
  return {
    id: asEntityId(dto.id),
    projectId: asEntityId(dto.project_id),
    parentRunId: asEntityId(dto.parent_run_id),
    parentRunRevision: dto.parent_run_revision,
    contractId: asEntityId(dto.contract_id),
    version: dto.version,
    status: dto.status,
    feedbackIds: dto.feedback_ids.map(asEntityId),
    baselineArtifactVersionIds:
      dto.baseline_artifact_version_ids.map(asEntityId),
    affectedArtifactVersionIds:
      dto.affected_artifact_version_ids.map(asEntityId),
    reusableArtifactVersionIds:
      dto.reusable_artifact_version_ids.map(asEntityId),
    recomputeSteps: [...dto.recompute_steps],
    versionDecisions: dto.version_decisions.map((item) => ({
      artifactVersionId: asEntityId(item.artifact_version_id),
      artifactId: asEntityId(item.artifact_id),
      artifactKind: item.artifact_kind,
      versionNumber: item.version_number,
      decision: item.decision,
      stepKey: item.step_key ?? null,
    })),
    conflicts: dto.conflicts.map((item) => ({
      code: item.code,
      artifactVersionId: item.artifact_version_id
        ? asEntityId(item.artifact_version_id)
        : null,
      detail: item.detail,
    })),
    confirmedRunId: dto.confirmed_run_id
      ? asEntityId(dto.confirmed_run_id)
      : null,
    createdAt: dto.created_at,
  };
}

export function createRevisionRepository(http: HttpClient): RevisionRepository {
  return {
    async createFeedback(input): Promise<UserFeedback> {
      const body: CreateUserFeedbackRequest = {
        expected_version_number: input.expectedVersionNumber,
        target_type: "artifact_version",
        target_id: input.artifactVersionId,
        target_locator: {},
        category: "correction",
        summary: input.summary,
        requested_change: input.requestedChange,
      };
      const payload = await http.post<unknown>(
        `/api/artifact-versions/${seg(input.artifactVersionId)}/feedback`,
        body,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return validateAndMap("UserFeedback", payload, mapFeedback);
    },
    async createPlan(input): Promise<RevisionPlan> {
      const body: CreateRevisionPlanRequest = {
        feedback_ids: [input.feedbackId],
        expected_parent_run_revision: input.expectedParentRunRevision,
      };
      const payload = await http.post<unknown>(
        `/api/projects/${seg(input.projectId)}/revision-plans`,
        body,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return validateAndMap("RevisionPlan", payload, mapPlan);
    },
    async confirmPlan(
      planId,
      expectedPlanVersion,
      idempotencyKey,
    ): Promise<ResearchRun> {
      const body: ConfirmRevisionPlanRequest = {
        expected_plan_version: expectedPlanVersion,
      };
      const payload = await http.post<unknown>(
        `/api/revision-plans/${seg(planId)}/confirm`,
        body,
        { "Idempotency-Key": idempotencyKey },
      );
      return validateAndMap("ResearchRun", payload, mapResearchRun);
    },
  };
}

export function createFixtureRevisionRepository(): RevisionRepository {
  const unsupported = (): never => {
    throw new FixtureSemanticError(
      "Revision writes are not available in Demo Replay; use the live HTTP repository.",
    );
  };
  return {
    createFeedback: async () => unsupported(),
    createPlan: async () => unsupported(),
    confirmPlan: async () => unsupported(),
  };
}
