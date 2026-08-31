/**
 * ResearchInput transport adapter.
 *
 * The Composer only sees the domain reference returned here. Multipart
 * framing, endpoint paths, DTO validation and server envelopes remain inside
 * this repository, alongside the other HTTP resource adapters.
 */

import type { ResearchInputRef as ResearchInputRefDto } from "@xingwen/contracts";
import {
  asEntityId,
  type DomainEntityId,
  type UtcIsoTimestamp,
} from "@xingwen/domain";

import { seg, validateAndMap, type HttpClient } from "./http-client";
import type {
  CreateResearchInputInput,
  ResearchInputRef,
  ResearchInputRepository,
  ResearchInputStatus,
  ResearchInputType,
} from "./ports";

export function mapResearchInputRef(
  dto: ResearchInputRefDto,
): ResearchInputRef {
  return {
    id: asEntityId(dto.id),
    type: dto.type as ResearchInputType,
    sourceType: dto.source_type,
    contentHash: dto.content_hash,
    filename: dto.filename ?? null,
    mimeType: dto.mime_type ?? null,
    sizeBytes: dto.size_bytes,
    createdAt: dto.created_at as UtcIsoTimestamp,
    sourceSnapshotId: dto.source_snapshot_id
      ? asEntityId(dto.source_snapshot_id)
      : null,
    status: (dto.status ?? "accepted") as ResearchInputStatus,
  };
}

function mapRef(payload: unknown): ResearchInputRef {
  return validateAndMap("ResearchInputRef", payload, mapResearchInputRef);
}

export function createResearchInputRepository(
  http: HttpClient,
): ResearchInputRepository {
  return {
    async create(input: CreateResearchInputInput): Promise<ResearchInputRef> {
      const form = new FormData();
      form.set("project_id", String(input.projectId));
      form.set("type", input.type);
      form.set("filename", input.filename);
      form.set("mime_type", input.mimeType);
      form.set("file", input.file, input.filename);
      const payload = await http.postMultipart<unknown>(
        "/api/research-inputs",
        form,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return mapRef(payload);
    },

    async list(
      projectId: DomainEntityId,
    ): Promise<readonly ResearchInputRef[]> {
      const page = await http.getPage<unknown>(
        `/api/research-inputs?project_id=${seg(projectId)}&limit=100`,
      );
      return page.data.map(mapRef);
    },

    async delete(inputId: DomainEntityId): Promise<void> {
      await http.delete(`/api/research-inputs/${seg(inputId)}`);
    },

    async bindToDraft(
      inputId: DomainEntityId,
      projectId: DomainEntityId,
      draftId: DomainEntityId,
    ): Promise<ResearchInputRef> {
      const payload = await http.post<unknown>(
        `/api/research-inputs/${seg(inputId)}/bind`,
        { project_id: projectId, contract_draft_id: draftId },
      );
      return mapRef(payload);
    },

    getContentUrl(inputId: DomainEntityId): string {
      return `/api/research-inputs/${seg(inputId)}/content`;
    },

    async getContent(inputId: DomainEntityId): Promise<Blob> {
      return http.getBlob(`/api/research-inputs/${seg(inputId)}/content`);
    },
  };
}
