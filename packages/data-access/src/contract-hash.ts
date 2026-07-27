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

const PYTHON_FLOAT_FIELDS = new Set([
  "evidence_requirements.minimum_coverage",
  "quality_constraints.source_completeness_min",
  "quality_constraints.unit_consistency_min",
]);

function pythonFloat(value: number): string {
  if (!Number.isFinite(value)) {
    throw new TypeError("Contract hash input must contain finite numbers");
  }
  if (Object.is(value, -0)) return "-0.0";
  if (Number.isInteger(value)) return `${value}.0`;

  const absolute = Math.abs(value);
  const raw =
    absolute > 0 && absolute < 1e-4 ? value.toExponential() : `${value}`;
  return raw.replace(
    /e([+-]?)(\d+)$/u,
    (_match, sign: string, digits: string) =>
      `e${sign || "+"}${digits.padStart(2, "0")}`,
  );
}

/** Stable serialization matching the backend's contract-specific JSON shape. */
function canonicalize(value: unknown, path: readonly string[] = []): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalize(item, path)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalize(record[key], [...path, key])}`,
      )
      .join(",")}}`;
  }
  if (typeof value === "number" && PYTHON_FLOAT_FIELDS.has(path.join("."))) {
    return pythonFloat(value);
  }
  const serialized = JSON.stringify(value);
  if (serialized === undefined) {
    throw new TypeError("Contract hash input must be JSON-serializable");
  }
  return serialized;
}

function toCanonicalJson(input: ResearchContractInput): string {
  return canonicalize(input);
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
