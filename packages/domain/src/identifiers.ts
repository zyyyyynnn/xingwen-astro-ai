/**
 * Branded primitive identifiers shared across the frontend domain model.
 *
 * These brands exist only at the TypeScript level; they carry no runtime
 * overhead. They prevent accidental mixing of identifier kinds (project id vs
 * run id vs artifact id) while remaining assignable from plain strings at the
 * repository boundary.
 */

declare const domainEntityIdBrand: unique symbol;

/**
 * Opaque identifier for any domain entity (project, run, artifact, …).
 *
 * Identifiers mirror the backend `Identifier` constraint: a non-empty trimmed
 * string of at most 128 characters. Repository adapters are responsible for
 * enforcing length/trim rules before handing values to the domain layer.
 */
export type DomainEntityId = string & {
  readonly [domainEntityIdBrand]: "DomainEntityId";
};

/**
 * Parse an untrusted identifier at a UI or transport boundary.
 *
 * Returns `null` instead of silently branding values that violate the backend
 * `Identifier` contract.
 */
export function parseEntityId(value: string): DomainEntityId | null {
  return value.length > 0 && value.length <= 128 && value.trim() === value
    ? (value as DomainEntityId)
    : null;
}

/** Convenience constructor used by adapters and fixtures. */
export function asEntityId(value: string): DomainEntityId {
  return value as DomainEntityId;
}
