/**
 * Private WorkspaceSnapshot recovery and Share repositories over `/api/v2`.
 *
 * Workspace `save` sends the contract-required integer `If-Match` (not a quoted
 * ETag), every response is validated against its generated schema and mapped
 * through the shared mapping layer, and the private single-share
 * read — which has no contract endpoint or consumer — is intentionally absent.
 */

import type {
  CreateShareSnapshotRequest,
  PublicShareSnapshot,
  ShareSnapshot,
  ShareSnapshotCreated,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";

import { HttpClient, seg, validateAndMap } from "./http-client";
import {
  mapCreateShareSnapshotRequestToDto,
  mapPublicShareSnapshot,
  mapShareSnapshot,
  mapShareSnapshotCreated,
  mapWorkspaceSnapshot,
  mapWorkspaceSnapshotInputToDto,
} from "./mapping";
import type { ShareRepository, WorkspaceSnapshotRepository } from "./ports";

interface SnapshotShareRepositories {
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
}

export function createSnapshotShareRepositories(
  http: HttpClient,
): SnapshotShareRepositories {
  const workspaces: WorkspaceSnapshotRepository = {
    async getByProjectId(projectId): Promise<WorkspaceSnapshot | null> {
      const payload = await http.get<unknown>(
        `/api/v2/projects/${seg(projectId)}/workspace-snapshot`,
      );
      return payload
        ? validateAndMap("WorkspaceSnapshot", payload, mapWorkspaceSnapshot)
        : null;
    },
    async save(
      projectId,
      snapshot: WorkspaceSnapshotInput,
      expectedRevision: number,
    ): Promise<WorkspaceSnapshot> {
      const payload = await http.put<unknown>(
        `/api/v2/projects/${seg(projectId)}/workspace-snapshot`,
        mapWorkspaceSnapshotInputToDto(snapshot),
        { "If-Match": String(expectedRevision) },
      );
      return validateAndMap("WorkspaceSnapshot", payload, mapWorkspaceSnapshot);
    },
  };

  const shares: ShareRepository = {
    async list(projectId): Promise<readonly ShareSnapshot[]> {
      const payloads = await http.list<unknown>(
        `/api/v2/projects/${seg(projectId)}/shares`,
      );
      return payloads.map((p) =>
        validateAndMap("ShareSnapshot", p, mapShareSnapshot),
      );
    },
    async create(
      projectId,
      request: CreateShareSnapshotRequest,
    ): Promise<ShareSnapshotCreated> {
      const payload = await http.post<unknown>(
        `/api/v2/projects/${seg(projectId)}/shares`,
        mapCreateShareSnapshotRequestToDto(request),
      );
      return validateAndMap(
        "ShareSnapshotCreated",
        payload,
        mapShareSnapshotCreated,
      );
    },
    async revoke(projectId, shareId): Promise<void> {
      await http.delete(
        `/api/v2/projects/${seg(projectId)}/shares/${seg(shareId)}`,
      );
    },
    async getPublic(shareToken): Promise<PublicShareSnapshot | null> {
      const payload = await http.get<unknown>(
        `/api/v2/shares/${seg(shareToken)}`,
      );
      return payload
        ? validateAndMap("PublicShareSnapshot", payload, mapPublicShareSnapshot)
        : null;
    },
  };

  return { workspaces, shares };
}
