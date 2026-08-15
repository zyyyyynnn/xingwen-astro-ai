import type {
  BindResearchInputToRunRequest,
  CreateResearchInputMultipartRequest,
  ResearchInputRef as ResearchInputRefDto,
  TextResearchInputRequest,
  UrlResearchInputRequest,
} from "@xingwen/contracts";
import type { ResearchInputRef } from "@xingwen/domain";

import { HttpClient, seg } from "./http-client";
import { mapResearchInputRef } from "./mapping";
import type { ResearchInputRepository } from "./ports";

const INPUT_PAGE_LIMIT = 100;

const CANONICAL_UPLOAD_MIME = {
  pdf: "application/pdf",
  csv: "text/csv",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  parquet: "application/vnd.apache.parquet",
  json: "application/json",
  image_dataset: "application/zip",
  fits: "application/fits",
} as const;

function uploadMime(
  input: Extract<
    Parameters<ResearchInputRepository["create"]>[0],
    { readonly content: ArrayBuffer }
  >,
): string {
  if (input.mimeType?.trim()) return input.mimeType;
  if (input.type !== "image") return CANONICAL_UPLOAD_MIME[input.type];
  const extension = input.filename.split(".").at(-1)?.toLowerCase();
  if (extension === "png") return "image/png";
  if (extension === "jpg" || extension === "jpeg") return "image/jpeg";
  if (extension === "gif") return "image/gif";
  if (extension === "webp") return "image/webp";
  return "application/octet-stream";
}

export function createResearchInputRepository(
  http: HttpClient,
): ResearchInputRepository {
  return {
    async listByProject(projectId): Promise<readonly ResearchInputRef[]> {
      const payloads = await http.list<ResearchInputRefDto>(
        `/api/research-inputs?project_id=${encodeURIComponent(String(projectId))}&limit=${String(INPUT_PAGE_LIMIT)}`,
      );
      return payloads.map(mapResearchInputRef);
    },
    async create(input): Promise<ResearchInputRef> {
      if (input.type === "text") {
        const body: TextResearchInputRequest = {
          project_id: String(input.projectId),
          type: "text",
          text_content: input.textContent,
          filename: input.filename ?? null,
          mime_type: input.mimeType ?? null,
        };
        const payload = await http.post<ResearchInputRefDto>(
          "/api/research-inputs",
          body,
          { "Idempotency-Key": input.idempotencyKey },
        );
        return mapResearchInputRef(payload);
      }
      if (input.type === "url") {
        const body: UrlResearchInputRequest = {
          project_id: String(input.projectId),
          type: "url",
          url: input.url,
          filename: input.filename ?? null,
          mime_type: input.mimeType ?? null,
        };
        const payload = await http.post<ResearchInputRefDto>(
          "/api/research-inputs",
          body,
          { "Idempotency-Key": input.idempotencyKey },
        );
        return mapResearchInputRef(payload);
      }
      const form = new FormData();
      const mimeType = uploadMime(input);
      const file = new Blob([input.content], {
        type: mimeType,
      });
      form.append("file", file, input.filename);
      const fields: CreateResearchInputMultipartRequest = {
        file: input.filename,
        filename: input.filename,
        mime_type: mimeType,
        project_id: String(input.projectId),
        type: input.type,
      };
      form.set("filename", fields.filename ?? input.filename);
      form.set("mime_type", mimeType);
      form.set("project_id", fields.project_id);
      form.set("type", fields.type);
      const payload = await http.postMultipart<ResearchInputRefDto>(
        "/api/research-inputs",
        form,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return mapResearchInputRef(payload);
    },
    async bindToRun(inputId, projectId, runId): Promise<ResearchInputRef> {
      const body: BindResearchInputToRunRequest = {
        project_id: String(projectId),
        run_id: String(runId),
        contract_draft_id: null,
      };
      const payload = await http.post<ResearchInputRefDto>(
        `/api/research-inputs/${seg(inputId)}/bind`,
        body,
      );
      return mapResearchInputRef(payload);
    },
  };
}
