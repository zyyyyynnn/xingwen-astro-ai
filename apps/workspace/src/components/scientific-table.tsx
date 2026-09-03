import type { DomainEntityId } from "@xingwen/domain";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Input,
} from "@xingwen/ui";
import {
  ChevronDown,
  ChevronUp,
  Search,
  TableProperties,
} from "@xingwen/ui/icons";
import { useMemo, useState } from "react";

export type ScientificTableScalar = string | number | boolean | null;

export interface ScientificTableColumn {
  readonly key: string;
  readonly label: string;
  readonly unit?: string | null;
  /** Layout intent drives the column's minimum width; defaults to "numeric" heuristics on value type. */
  readonly variant?: "identity" | "numeric" | "descriptive";
}

export interface ScientificTableCell {
  readonly value: ScientificTableScalar;
  readonly unit?: string | null;
  readonly status?: "mapped" | "missing" | "unresolved";
  readonly reason?: string | null;
  readonly evidenceIds?: readonly DomainEntityId[];
}

export interface ScientificTableRow {
  readonly id: string;
  readonly identity?: string | null;
  readonly cells: Readonly<Record<string, ScientificTableCell>>;
}

function displayValue(value: ScientificTableScalar): string {
  if (value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

const COLUMN_MIN_WIDTH: Record<
  NonNullable<ScientificTableColumn["variant"]>,
  string
> = {
  identity: "scientific-table__column--identity",
  numeric: "scientific-table__column--numeric",
  descriptive: "scientific-table__column--descriptive",
};

const UNIT_LABELS: Readonly<Record<string, string>> = {
  none: "",
  dimensionless: "",
  earth_radius: "R⊕",
  earth_mass: "M⊕",
  solar_radius: "R☉",
  solar_mass: "M☉",
  jupiter_radius: "R♃",
  jupiter_mass: "M♃",
  r_earth: "R⊕",
  m_earth: "M⊕",
  r_sun: "R☉",
  m_sun: "M☉",
  k: "K",
  kelvin: "K",
  day: "天",
  days: "天",
  dex: "dex",
  degree: "°",
  degrees: "°",
};

export function formatScientificUnit(unit: string | null | undefined): string {
  if (!unit) return "";
  const normalized = unit.trim().replace(/^_+/u, "").toLowerCase();
  return UNIT_LABELS[normalized] ?? unit.replace(/^_+/u, "");
}

function columnMinWidthClass(
  column: ScientificTableColumn,
  sampleValues: readonly ScientificTableScalar[],
): string {
  if (column.variant) {
    return COLUMN_MIN_WIDTH[column.variant];
  }
  const numeric = sampleValues.some(
    (value) => typeof value === "number" || typeof value === "boolean",
  );
  return numeric ? COLUMN_MIN_WIDTH.numeric : COLUMN_MIN_WIDTH.identity;
}

function Cell({ cell }: { readonly cell: ScientificTableCell | undefined }) {
  if (!cell) return <>—</>;
  if (cell.status === "missing") return <>—</>;
  if (cell.status === "unresolved") {
    return (
      <span className="inline-flex items-center gap-1">
        <Badge variant="destructive">未解析</Badge>
        {cell.reason ? (
          <small className="ui-text-label text-[var(--color-ink-secondary)]">
            {cell.reason}
          </small>
        ) : null}
      </span>
    );
  }
  const unit = formatScientificUnit(cell.unit);
  return (
    <span>
      {displayValue(cell.value)}
      {unit ? (
        <small className="ui-text-label text-[var(--color-ink-secondary)]">
          {" "}
          {unit}
        </small>
      ) : null}
    </span>
  );
}

export function ScientificTable({
  caption,
  columns: suppliedColumns,
  rows: suppliedRows,
  maxRows,
  maxColumns,
  totalRowCount = suppliedRows.length,
  totalColumnCount = suppliedColumns.length,
  showIdentity = false,
  onSelectEvidence,
}: {
  readonly caption: string;
  readonly columns: readonly ScientificTableColumn[];
  readonly rows: readonly ScientificTableRow[];
  readonly maxRows: number;
  readonly maxColumns: number;
  readonly totalRowCount?: number;
  readonly totalColumnCount?: number;
  readonly showIdentity?: boolean;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
}) {
  const allColumns = suppliedColumns.slice(0, maxColumns);
  const [hiddenFields, setHiddenFields] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [sort, setSort] = useState<{
    key: string;
    direction: "asc" | "desc";
  } | null>(null);
  const [query, setQuery] = useState("");
  const columns = allColumns.filter((column) => !hiddenFields.has(column.key));
  const rows = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("zh-Hans");
    const filtered = normalizedQuery
      ? suppliedRows.filter((row) =>
          [
            row.identity ?? "",
            ...Object.values(row.cells).map((cell) => displayValue(cell.value)),
          ].some((value) =>
            value.toLocaleLowerCase("zh-Hans").includes(normalizedQuery),
          ),
        )
      : suppliedRows;
    const bounded = filtered.slice(0, maxRows);
    if (sort === null) return bounded;
    return [...bounded].sort((left, right) => {
      const a = left.cells[sort.key]?.value ?? "";
      const b = right.cells[sort.key]?.value ?? "";
      const numeric = Number(a) - Number(b);
      const comparison =
        Number.isNaN(numeric) || a === "" || b === ""
          ? String(a).localeCompare(String(b), "zh-Hans")
          : numeric;
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [maxRows, query, sort, suppliedRows]);

  const toggleSort = (key: string) => {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: "asc" };
      if (current.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  };
  const toggleColumn = (key: string) => {
    setHiddenFields((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else if (next.size < allColumns.length - 1) next.add(key);
      return next;
    });
  };

  // Column layout intent comes from what the data actually holds, not a
  // uniform 1fr squeeze that forces vertical CJK headers.
  const columnWidthClass = new Map<string, string>();
  for (const column of allColumns) {
    const samples = suppliedRows
      .slice(0, 8)
      .map((row) => row.cells[column.key]?.value ?? null);
    columnWidthClass.set(column.key, columnMinWidthClass(column, samples));
  }
  const identityWidthClass = COLUMN_MIN_WIDTH.identity;

  return (
    <div className="scientific-table my-2 overflow-x-auto bg-[var(--color-surface)]">
      <div className="scientific-table__toolbar">
        <div className="scientific-table__search">
          <Search aria-hidden="true" />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索当前数据…"
            aria-label="搜索当前数据"
          />
        </div>
        <div className="scientific-table__toolbar-actions">
          <span className="scientific-table__scroll-hint">
            {query
              ? `${rows.length} 条匹配`
              : `${totalRowCount} 行 · ${columns.length} 列`}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="small" variant="secondary">
                <TableProperties aria-hidden="true" />
                选择列
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="max-h-72 overflow-y-auto"
            >
              {allColumns.map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.key}
                  checked={!hiddenFields.has(column.key)}
                  onCheckedChange={() => toggleColumn(column.key)}
                >
                  {column.label}
                  {formatScientificUnit(column.unit)
                    ? ` (${formatScientificUnit(column.unit)})`
                    : ""}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <table className="ui-text-body w-full min-w-max text-left border-collapse">
        <caption className="sr-only">{caption}</caption>
        <thead className="scientific-table__head sticky top-0">
          <tr className="border-b bg-[var(--color-surface-muted)] border-[var(--color-border)]">
            {showIdentity ? (
              <th
                scope="col"
                className={`scientific-table__identity p-2 ${identityWidthClass}`}
              >
                标识 / 主体
              </th>
            ) : null}
            {columns.map((column) => (
              <th
                scope="col"
                key={column.key}
                className={`p-2 font-medium whitespace-nowrap ${columnWidthClass.get(column.key) ?? ""}`}
              >
                <Button
                  variant="ghost"
                  size="inline"
                  aria-label={
                    formatScientificUnit(column.unit)
                      ? `${column.label} (${formatScientificUnit(column.unit)})`
                      : column.label
                  }
                  onClick={() => toggleSort(column.key)}
                >
                  <span>{column.label}</span>
                  {formatScientificUnit(column.unit) ? (
                    <small>{formatScientificUnit(column.unit)}</small>
                  ) : null}
                  {sort?.key === column.key ? (
                    sort.direction === "asc" ? (
                      <ChevronUp aria-hidden="true" />
                    ) : (
                      <ChevronDown aria-hidden="true" />
                    )
                  ) : null}
                </Button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border)]">
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-[var(--color-surface-muted)]">
              {showIdentity ? (
                <th
                  scope="row"
                  className={`scientific-table__identity p-2 whitespace-nowrap ${identityWidthClass}`}
                >
                  {row.identity || "未命名记录"}
                </th>
              ) : null}
              {columns.map((column) => {
                const cell = row.cells[column.key];
                const evidenceIds = cell?.evidenceIds ?? [];
                const numericCell =
                  column.variant === "numeric" ||
                  typeof cell?.value === "number" ||
                  typeof cell?.value === "boolean";
                return (
                  <td
                    key={column.key}
                    className={`p-2 ${numericCell ? "tabular-nums" : ""}`}
                  >
                    {evidenceIds.length > 0 && onSelectEvidence ? (
                      <Button
                        variant="ghost"
                        size="inline"
                        className="underline-offset-2 hover:underline focus-visible:underline"
                        title="查看该数值的证据"
                        onClick={() => onSelectEvidence(evidenceIds)}
                      >
                        <Cell cell={cell} />
                      </Button>
                    ) : (
                      <Cell cell={cell} />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {totalRowCount > rows.length || totalColumnCount > allColumns.length ? (
        <p className="ui-text-label p-2 text-[var(--color-ink-secondary)] bg-[var(--color-surface-muted)] border-t border-[var(--color-border)]">
          {totalRowCount > rows.length
            ? `显示前 ${rows.length} / ${totalRowCount} 行`
            : `${totalRowCount} 行`}
          {totalColumnCount > allColumns.length
            ? ` · 前 ${allColumns.length} / ${totalColumnCount} 列`
            : null}
        </p>
      ) : null}
    </div>
  );
}
