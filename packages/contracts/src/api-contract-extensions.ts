/**
 * API_CONTRACT.md-sourced request/response types for endpoints not yet in the
 * generated OpenAPI.
 *
 * These types are NOT generated from `packages/schemas/generated/v2-core/openapi.json`.
 * They are authored by hand from `docs/architecture/API_CONTRACT.md` §7-§13 to give
 * the HTTP adapter type-safe request bodies before the backend exposes the
 * corresponding routes. When the backend implements these endpoints and the
 * OpenAPI is regenerated, these types will be superseded by generated
 * equivalents and this file should be deleted.
 *
 * Source of truth: docs/architecture/API_CONTRACT.md
 */

import type {
  ContractDraftStatus,
  ResearchContractInput,
} from "./generated/v2-core/dto";

/**
 * PATCH /api/v2/research-contract-drafts/{draft_id} request body.
 *
 * API_CONTRACT.md §7: "请求携带 `If-Match` 或 `version`，防止多个编辑器静默覆盖。"
 * The generated `UpdateResearchContractDraftRequest` only has `contract` and
 * `intent`; this extension adds `version` (for optimistic concurrency) and
 * `status` (for draft→confirmed transitions).
 */
export interface UpdateContractDraftRequestExt {
  readonly version: number;
  readonly contract?: ResearchContractInput | null;
  readonly intent?: string | null;
  readonly status?: ContractDraftStatus;
}

/**
 * PATCH /api/v2/projects/{project_id} request body.
 *
 * API_CONTRACT.md §8: "修改名称、描述等非科研产物元信息"
 */
export interface UpdateProjectRequest {
  readonly name?: string;
  readonly description?: string;
}
