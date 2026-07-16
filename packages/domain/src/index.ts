declare const domainEntityIdBrand: unique symbol;

export type DomainEntityId = string & {
  readonly [domainEntityIdBrand]: "DomainEntityId";
};

/** Public domain boundary only. Scientific entities are introduced by their owning issues. */
export interface DomainBoundary {
  readonly implementationStatus: "pending";
}
