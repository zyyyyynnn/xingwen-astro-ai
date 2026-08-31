export interface ScientificFactItem {
  readonly label: string;
  readonly value: string | readonly string[];
}

export interface ScientificFactGridProps {
  readonly facts: readonly ScientificFactItem[];
  readonly className?: string;
  readonly columns?: 1 | 2 | 3 | 4;
}

export function ScientificFactGrid({
  facts,
  className = "",
  columns = 2,
}: ScientificFactGridProps) {
  if (facts.length === 0) return null;

  const colClass =
    columns === 1
      ? "grid-cols-1"
      : columns === 3
        ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
        : columns === 4
          ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
          : "grid-cols-1 sm:grid-cols-2";

  return (
    <dl
      className={`xw-fact-grid grid gap-x-6 gap-y-2.5 py-1.5 text-sm ${colClass} ${className}`}
    >
      {facts.map((fact) => {
        const values = Array.isArray(fact.value) ? fact.value : [fact.value];
        if (values.length === 0 || values.every((v) => !v)) return null;
        return (
          <div key={fact.label} className="flex flex-col gap-0.5 py-0.5">
            <dt className="text-xs font-medium">{fact.label}</dt>
            <dd className="text-xs">{values.join("；")}</dd>
          </div>
        );
      })}
    </dl>
  );
}
