import { queryOptions } from "@tanstack/react-query";
import { EntityNotFoundError } from "@xingwen/data-access/errors";
import type { RepositorySet } from "@xingwen/data-access/ports";
import type {
  ArtifactVersionSummary,
  DataArtifactKind,
  DataArtifactReview,
  DomainEntityId,
  GraphArtifactReview,
  LiteratureArtifactReview,
  PaperAcquisitionReview,
  PaperSummaryDocumentSourceReview,
  PaperSummaryReview,
  ScientificArtifactReview,
} from "@xingwen/domain";
import type {
  ActivityPresentationEvent,
  ArtifactVersionMetadataViewModel,
  DataArtifactReviewViewModel,
  EvidenceViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
  ProjectViewModel,
  ResearchAdapter,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchPlanningCatalogViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  RunCheckpointViewModel,
  RunStepViewModel,
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";

interface WorkspaceQueriesDependencies {
  readonly repositories: Pick<
    RepositorySet,
    | "projects"
    | "researchCatalog"
    | "contracts"
    | "runs"
    | "researchThread"
    | "researchInputs"
    | "artifacts"
    | "paperSummary"
    | "paperAcquisition"
    | "dataArtifacts"
    | "literatureArtifacts"
    | "graphArtifacts"
    | "scientificArtifacts"
  >;
  readonly researchAdapter: ResearchAdapter;
}

export interface RunEventFeedCache {
  readonly events: readonly ActivityPresentationEvent[];
  readonly cursor: string | null;
  readonly lastSequence: number;
  readonly latestSequence: number;
  readonly error: unknown | null;
}

export const EMPTY_RUN_EVENT_FEED: RunEventFeedCache = Object.freeze({
  events: [],
  cursor: null,
  lastSequence: 0,
  latestSequence: 0,
  error: null,
});

async function requireEntity<T>(
  kind: string,
  id: DomainEntityId,
  read: () => Promise<T | null>,
): Promise<T> {
  const entity = await read();
  if (entity === null) throw new EntityNotFoundError(kind, id);
  return entity;
}

function requireProjectOwnership(
  kind: string,
  projectId: DomainEntityId,
  entityProjectId: DomainEntityId,
): void {
  if (entityProjectId !== projectId) {
    throw new EntityNotFoundError(kind, projectId);
  }
}

export function createWorkspaceQueries({
  repositories,
  researchAdapter,
}: WorkspaceQueriesDependencies) {
  return Object.freeze({
    projects: () =>
      queryOptions({
        queryKey: workspaceQueryKeys.projects(),
        queryFn: async (): Promise<readonly ProjectViewModel[]> => {
          const projects: ProjectViewModel[] = [];
          const seenCursors = new Set<string>();
          let cursor: string | null = null;
          do {
            const page = await repositories.projects.list(cursor);
            projects.push(
              ...page.items.map(researchAdapter.toProjectViewModel),
            );
            if (page.nextCursor && seenCursors.has(page.nextCursor)) {
              throw new Error("Project listing returned a repeated cursor.");
            }
            if (page.nextCursor) seenCursors.add(page.nextCursor);
            cursor = page.nextCursor;
          } while (cursor !== null);
          return projects;
        },
      }),
    project: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.project(projectId),
        queryFn: async (): Promise<ProjectViewModel> =>
          researchAdapter.toProjectViewModel(
            await requireEntity("ResearchProject", projectId, () =>
              repositories.projects.getById(projectId),
            ),
          ),
      }),
    researchCatalog: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.researchCatalog(projectId),
        queryFn: async (): Promise<ResearchPlanningCatalogViewModel> =>
          repositories.researchCatalog.getForProject(projectId),
      }),
    researchInputs: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.researchInputs(projectId),
        queryFn: () => repositories.researchInputs.list(projectId),
      }),
    thread: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.thread(projectId),
        queryFn: async (): Promise<readonly ResearchThreadEntryViewModel[]> => {
          const entries: ResearchThreadEntryViewModel[] = [];
          let cursor: string | null = null;
          const seen = new Set<string>();
          do {
            const page = await repositories.researchThread.list(
              projectId,
              cursor,
            );
            entries.push(
              ...page.items.map(researchAdapter.toResearchThreadEntryViewModel),
            );
            if (page.nextCursor !== null && seen.has(page.nextCursor)) {
              throw new Error("Research Thread returned a repeated cursor.");
            }
            if (page.nextCursor !== null) seen.add(page.nextCursor);
            cursor = page.nextCursor;
          } while (cursor !== null);
          return entries;
        },
      }),
    draft: (projectId: DomainEntityId, draftId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.draft(projectId, draftId),
        queryFn: async (): Promise<ResearchContractDraftViewModel> =>
          researchAdapter.toContractDraftViewModel(
            await requireEntity("ResearchContractDraft", draftId, () =>
              repositories.contracts.getDraftById(draftId),
            ),
          ),
      }),
    contract: (projectId: DomainEntityId, contractId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.contract(projectId, contractId),
        queryFn: async (): Promise<ResearchContractViewModel> =>
          researchAdapter.toContractViewModel(
            await requireEntity("ResearchContract", contractId, () =>
              repositories.contracts.getContractById(contractId),
            ),
          ),
      }),
    run: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.run(projectId, runId),
        queryFn: async (): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await requireEntity("ResearchRun", runId, () =>
              repositories.runs.getById(runId),
            ),
          ),
      }),
    runEvents: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runEvents(projectId, runId),
        queryFn: async (): Promise<RunEventFeedCache> => EMPTY_RUN_EVENT_FEED,
        initialData: EMPTY_RUN_EVENT_FEED,
        enabled: false,
      }),
    runSteps: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runSteps(projectId, runId),
        queryFn: async (): Promise<readonly RunStepViewModel[]> =>
          (await repositories.runs.listSteps(runId)).map(
            researchAdapter.toRunStepViewModel,
          ),
      }),
    checkpoint: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runCheckpoint(projectId, runId),
        queryFn: async (): Promise<RunCheckpointViewModel | null> => {
          const checkpoint = await repositories.runs.getCheckpoint(runId);
          return checkpoint === null
            ? null
            : researchAdapter.toRunCheckpointViewModel(checkpoint);
        },
      }),
    artifactsByRun: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.artifactsByRun(projectId, runId),
        queryFn: async (): Promise<readonly ResearchArtifactViewModel[]> => {
          const artifacts = await repositories.artifacts.listByRun(runId);
          for (const artifact of artifacts) {
            requireProjectOwnership(
              "ResearchArtifact",
              projectId,
              artifact.projectId,
            );
          }
          return artifacts.map(researchAdapter.toArtifactViewModel);
        },
      }),
    artifact: (projectId: DomainEntityId, artifactId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.artifact(projectId, artifactId),
        queryFn: async (): Promise<ResearchArtifactViewModel> => {
          const artifact = await requireEntity(
            "ResearchArtifact",
            artifactId,
            () => repositories.artifacts.getArtifact(artifactId),
          );
          requireProjectOwnership(
            "ResearchArtifact",
            projectId,
            artifact.projectId,
          );
          return researchAdapter.toArtifactViewModel(artifact);
        },
      }),
    artifactVersions: (projectId: DomainEntityId, artifactId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.artifactVersions(projectId, artifactId),
        queryFn: async (): Promise<readonly ArtifactVersionSummary[]> => {
          const versions =
            await repositories.artifacts.listVersions(artifactId);
          for (const version of versions) {
            if (version.artifactId !== artifactId) {
              throw new Error("ArtifactVersion ownership is invalid.");
            }
          }
          return versions;
        },
      }),
    artifactVersion: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.artifactVersion(
          projectId,
          artifactVersionId,
        ),
        queryFn: async (): Promise<ArtifactVersionMetadataViewModel> => {
          const version = await requireEntity(
            "ArtifactVersion",
            artifactVersionId,
            () => repositories.artifacts.getVersion(artifactVersionId),
          );
          requireProjectOwnership(
            "ArtifactVersion",
            projectId,
            version.projectId,
          );
          return researchAdapter.toArtifactVersionViewModel(version);
        },
      }),
    paperSummary: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.paperSummary(projectId, artifactVersionId),
        queryFn: async (): Promise<PaperSummaryReview> => {
          const summary =
            await repositories.paperSummary.getSummary(artifactVersionId);
          requireProjectOwnership("PaperSummary", projectId, summary.projectId);
          if (summary.artifactVersionId !== artifactVersionId) {
            throw new EntityNotFoundError("PaperSummary", artifactVersionId);
          }
          return summary;
        },
      }),
    paperSummaryDocumentSource: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.paperSummaryDocumentSource(
          projectId,
          artifactVersionId,
        ),
        queryFn: async (): Promise<PaperSummaryDocumentSourceReview> =>
          // Ownership is enforced by the session-scoped backend read (it
          // validates the full summary provenance before resolving the
          // authorized PaperCandidate → ResearchInput binding); a foreign
          // version surfaces as a typed NotFound.
          repositories.paperSummary.getDocumentSource(artifactVersionId),
      }),
    evidence: (projectId: DomainEntityId, evidenceId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.evidence(projectId, evidenceId),
        queryFn: async (): Promise<EvidenceViewModel> => {
          const evidence = await requireEntity("Evidence", evidenceId, () =>
            repositories.artifacts.getEvidence(evidenceId),
          );
          const version = await requireEntity(
            "ArtifactVersion",
            evidence.artifactVersionId,
            () => repositories.artifacts.getVersion(evidence.artifactVersionId),
          );
          if (version.projectId) {
            requireProjectOwnership("Evidence", projectId, version.projectId);
          }
          return researchAdapter.toEvidenceViewModel(evidence);
        },
      }),
    dataArtifact: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
      kind: DataArtifactKind,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.dataArtifact(
          projectId,
          artifactVersionId,
          kind,
        ),
        queryFn: async (): Promise<DataArtifactReviewViewModel> => {
          const review: DataArtifactReview =
            kind === "dataset"
              ? await repositories.dataArtifacts.getDataset(artifactVersionId)
              : kind === "field_dictionary"
                ? await repositories.dataArtifacts.getFieldDictionary(
                    artifactVersionId,
                  )
                : await repositories.dataArtifacts.getSourceCollection(
                    artifactVersionId,
                  );
          requireProjectOwnership("DataArtifact", projectId, review.projectId);
          if (
            review.artifactVersionId !== artifactVersionId ||
            review.kind !== kind
          ) {
            throw new EntityNotFoundError("DataArtifact", artifactVersionId);
          }
          return researchAdapter.toDataArtifactViewModel(review);
        },
      }),
    paperAcquisition: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.paperAcquisition(
          projectId,
          artifactVersionId,
        ),
        queryFn: async (): Promise<PaperAcquisitionReviewViewModel> => {
          const review: PaperAcquisitionReview =
            await repositories.paperAcquisition.getReview(artifactVersionId);
          requireProjectOwnership(
            "PaperCollection",
            projectId,
            review.projectId,
          );
          if (review.artifactVersionId !== artifactVersionId) {
            throw new EntityNotFoundError("PaperCollection", artifactVersionId);
          }
          return researchAdapter.toPaperAcquisitionViewModel(review);
        },
      }),
    literatureArtifact: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
      kind: "literature_claims" | "literature_relations" | "reasoning_traces",
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.literatureArtifact(
          projectId,
          artifactVersionId,
          kind,
        ),
        queryFn: async (): Promise<LiteratureArtifactReviewViewModel> => {
          const review: LiteratureArtifactReview =
            kind === "literature_claims"
              ? await repositories.literatureArtifacts.getClaims(
                  artifactVersionId,
                )
              : kind === "literature_relations"
                ? await repositories.literatureArtifacts.getRelations(
                    artifactVersionId,
                  )
                : await repositories.literatureArtifacts.getReasoningTraces(
                    artifactVersionId,
                  );
          requireProjectOwnership(
            "LiteratureArtifact",
            projectId,
            review.projectId,
          );
          if (
            review.artifactVersionId !== artifactVersionId ||
            review.kind !== kind
          ) {
            throw new EntityNotFoundError(
              "LiteratureArtifact",
              artifactVersionId,
            );
          }
          return researchAdapter.toLiteratureArtifactViewModel(review);
        },
      }),
    graphArtifact: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.graphArtifact(
          projectId,
          artifactVersionId,
        ),
        queryFn: async (): Promise<GraphArtifactReviewViewModel> => {
          const review: GraphArtifactReview =
            await repositories.graphArtifacts.getReview(artifactVersionId);
          requireProjectOwnership("GraphArtifact", projectId, review.projectId);
          if (
            review.artifactVersionId !== artifactVersionId ||
            review.kind !== "graph"
          ) {
            throw new EntityNotFoundError("GraphArtifact", artifactVersionId);
          }
          return researchAdapter.toGraphArtifactViewModel(review);
        },
      }),
    scientificArtifact: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
      kind:
        | "analysis_report"
        | "visualization"
        | "spectrum"
        | "light_curve"
        | "model_evaluation"
        | "model_artifact",
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.scientificArtifact(
          projectId,
          artifactVersionId,
          kind,
        ),
        queryFn: async (): Promise<ScientificArtifactReview> => {
          const review: ScientificArtifactReview =
            await repositories.scientificArtifacts.getReview(artifactVersionId);
          requireProjectOwnership(
            "ScientificArtifact",
            projectId,
            review.projectId,
          );
          if (
            review.artifactVersionId !== artifactVersionId ||
            review.content.kind !== kind
          ) {
            throw new EntityNotFoundError(
              "ScientificArtifact",
              artifactVersionId,
            );
          }
          return review;
        },
      }),
  });
}

export type WorkspaceQueries = ReturnType<typeof createWorkspaceQueries>;
