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

/** Convenience constructor used by adapters and fixtures. */
export function asEntityId(value: string): DomainEntityId {
  return value as DomainEntityId;
}
