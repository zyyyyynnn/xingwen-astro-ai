/**
 * Canonical content hash for a research contract input.
 *
 * Mirrors the backend `canonical_request_hash` semantics in
 * `apps/api/src/app/security.py`: canonical JSON (sorted keys, `,`/`:`
 * separators, no ASCII escaping) over the contract input fields, then
 * SHA-256. The hash covers only the scientific payload — `id`,
 * `project_id`, `version`, `created_from_draft_id`, `created_at` and
 * `content_hash` itself are excluded so two contracts with identical
 * research content share the same hash regardless of identity metadata.
 *
 * Uses the Web Crypto `SubtleCrypto.digest` API, which is available in both
 * Node 24 (global `crypto`) and browsers, with no new dependency.
 */

import type { ResearchContractInput } from "@xingwen/contracts";

/** Stable key order independent of insertion order. */
function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[key] = canonicalize((value as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return value;
}

function toCanonicalJson(input: ResearchContractInput): string {
  return JSON.stringify(canonicalize(input));
}

/**
 * Compute the canonical SHA-256 content hash of a contract input.
 *
 * @returns a `sha256:<hex>` content hash, deterministic for identical input
 *   content and distinct for any valid content change.
 */
export async function computeContractContentHash(
  input: ResearchContractInput,
): Promise<string> {
  const data = new TextEncoder().encode(toCanonicalJson(input));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", data);
  const bytes = new Uint8Array(digest);
  let hex = "";
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, "0");
  }
  return `sha256:${hex}`;
}
