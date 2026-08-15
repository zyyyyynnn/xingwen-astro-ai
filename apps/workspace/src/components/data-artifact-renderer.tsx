import type { DomainEntityId } from "@xingwen/domain";
import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  DatasetCellReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";
import { Badge, Button, Checkbox } from "@xingwen/ui";
import { useMemo, useState } from "react";

export type DataArtifactSurface = "thread" | "docked" | "fullscreen";

export interface DataArtifactRendererProps {
  readonly review: DataArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
}

const SURFACE_LIMITS: Record<
  DataArtifactSurface,
  { readonly rows: number; readonly columns: number; readonly fields: number }
> = {
  thread: { rows: 4, columns: 6, fields: 4 },
  docked: { rows: 40, columns: 16, fields: 40 },
  fullscreen: { rows: 100, columns: 24, fields: 100 },
};

const COMPACT_SURFACES: readonly DataArtifactSurface[] = ["thread"];

function displayValue(value: string | null): string {
  return value === null || value.trim() === "" ? "—" : value;
}

function sourceModeLabel(mode: string): string {
  if (mode === "live") return "实时数据";
  if (mode === "cached") return "缓存数据";
  return "演示数据";
}

function fieldLabel(field: DataArtifactFieldDefinitionViewModel): string {
  return field.meaningZh || field.labelEn || field.fieldId;
}

function ArtifactMetadata({
  review,
  surface,
}: {
  readonly review: DataArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
}) {
  const retrievedAt = review.sourceSnapshots
    .map((snapshot) => snapshot.retrievedAt)
    .sort()
    .at(-1);
  return (
    <dl className="data-artifact__metadata">
      <div>
        <dt>来源模式</dt>
        <dd>{sourceModeLabel(review.sourceMode)}</dd>
      </div>
      <div>
        <dt>来源</dt>
        <dd>
          {[...new Set(review.sourceSnapshots.map((s) => s.sourceId))].join(
            "、",
          ) || "未提供"}
        </dd>
      </div>
      {retrievedAt ? (
        <div>
          <dt>数据获取时间</dt>
          <dd>{retrievedAt}</dd>
        </div>
      ) : null}
      <div>
        <dt>质量</dt>
        <dd>{review.quality.status === "pass" ? "已通过" : "未提供"}</dd>
      </div>
      {surface === "fullscreen" ? (
        <div>
          <dt>证据</dt>
          <dd>{review.evidenceIds.length}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function CellValue({ cell }: { readonly cell: DatasetCellReviewViewModel }) {
  if (cell.status === "mapped") {
    return (
      <span>
        {displayValue(cell.value)}
        {cell.unit ? (
          <small className="data-artifact__unit"> {cell.unit}</small>
        ) : null}
      </span>
    );
  }
  return (
    <span className="data-artifact__null-cell">
      <Badge variant={cell.status === "unresolved" ? "destructive" : "outline"}>
        {cell.status === "unresolved" ? "未解析" : "空值"}
      </Badge>
      {cell.reason ? <small>{cell.reason}</small> : null}
    </span>
  );
}

type SortDirection = "asc" | "desc";

function DatasetTable({
  review,
  surface,
  onSelectEvidence,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
}) {
  const limits = SURFACE_LIMITS[surface];
  const compact = COMPACT_SURFACES.includes(surface);
  const allColumns = review.columns.slice(0, limits.columns);
  const [hiddenFields, setHiddenFields] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [sort, setSort] = useState<{
    field: string;
    direction: SortDirection;
  } | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);

  const columns = allColumns.filter(
    (column) => !hiddenFields.has(String(column.fieldId)),
  );

  const rows = useMemo(() => {
    const base = review.rows.slice(0, limits.rows);
    if (sort === null) return base;
    const cellValue = (row: (typeof base)[number]) => {
      const cell = row.cells.find(
        (item) => String(item.canonicalFieldId) === sort.field,
      );
      return cell?.value ?? "";
    };
    return [...base].sort((left, right) => {
      const a = cellValue(left);
      const b = cellValue(right);
      const numeric = Number(a) - Number(b);
      const outcome =
        Number.isNaN(numeric) || a.trim() === "" || b.trim() === ""
          ? a.localeCompare(b, "zh-Hans")
          : numeric;
      return sort.direction === "asc" ? outcome : -outcome;
    });
  }, [review.rows, limits.rows, sort]);

  const toggleSort = (fieldId: string) => {
    setSort((current) => {
      if (current?.field !== fieldId)
        return { field: fieldId, direction: "asc" };
      if (current.direction === "asc")
        return { field: fieldId, direction: "desc" };
      return null;
    });
  };

  const toggleColumn = (fieldId: string) => {
    setHiddenFields((current) => {
      const next = new Set(current);
      if (next.has(fieldId)) {
        next.delete(fieldId);
      } else if (next.size < allColumns.length - 1) {
        next.add(fieldId);
      }
      return next;
    });
  };

  return (
    <div className="data-artifact__table-scroll">
      {compact ? null : (
        <div
          className="data-artifact__column-control"
          aria-label="数据列显示控制"
        >
          {allColumns.map((column) => {
            const fieldId = String(column.fieldId);
            return (
              <label key={column.fieldId} htmlFor={`column-${fieldId}`}>
                <Checkbox
                  id={`column-${fieldId}`}
                  checked={!hiddenFields.has(fieldId)}
                  onCheckedChange={() => toggleColumn(fieldId)}
                />
                {fieldLabel(column)}
              </label>
            );
          })}
        </div>
      )}
      <table className="data-artifact__table">
        <caption className="sr-only">研究数据集中的规范化字段与数据行</caption>
        <thead>
          <tr>
            <th scope="col">行</th>
            {columns.map((column) => (
              <th scope="col" key={column.fieldId}>
                <Button
                  variant="ghost"
                  className="data-artifact__sort"
                  onClick={() => toggleSort(String(column.fieldId))}
                >
                  {fieldLabel(column)}
                  {sort?.field === String(column.fieldId)
                    ? sort.direction === "asc"
                      ? " ↑"
                      : " ↓"
                    : ""}
                </Button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const cells = new Map(
              row.cells.map((cell) => [String(cell.canonicalFieldId), cell]),
            );
            return (
              <tr
                key={row.rowId}
                data-selected={selectedRowId === row.rowId}
                onClick={() => {
                  setSelectedRowId(
                    selectedRowId === row.rowId ? null : row.rowId,
                  );
                  onSelectEvidence?.(row.evidenceIds);
                }}
              >
                <th scope="row" title={row.identity || undefined}>
                  {row.identity || row.rowId}
                </th>
                {columns.map((column) => {
                  const cell = cells.get(String(column.fieldId));
                  return (
                    <td key={column.fieldId}>
                      {cell ? (
                        cell.evidenceIds.length > 0 && onSelectEvidence ? (
                          <Button
                            variant="ghost"
                            className="data-artifact__cell-evidence"
                            title="查看该数值的证据"
                            onClick={(event) => {
                              event.stopPropagation();
                              onSelectEvidence(cell.evidenceIds);
                            }}
                          >
                            <CellValue cell={cell} />
                          </Button>
                        ) : (
                          <CellValue cell={cell} />
                        )
                      ) : (
                        "—"
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {review.rows.length > rows.length ? (
        <p className="data-artifact__table-note">
          当前显示前 {rows.length} / {review.rowCount} 行。
        </p>
      ) : null}
    </div>
  );
}

function DatasetRenderer({
  review,
  title,
  surface,
  onSelectEvidence,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
}) {
  return (
    <article
      className="data-artifact data-artifact--dataset"
      data-surface={surface}
    >
      <header className="data-artifact__header">
        <div>
          <h3>{title}</h3>
          <p className="data-artifact__subtitle">
            数据表 · {review.rowCount} 行 · {review.fieldCount} 个字段
            {review.conflictCount > 0 ? ` · 冲突 ${review.conflictCount}` : ""}
          </p>
        </div>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      {review.rows.length > 0 && review.columns.length > 0 ? (
        <DatasetTable
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <p className="data-artifact__empty">
          当前版本没有可展示的数据行或字段。
        </p>
      )}
    </article>
  );
}

function fieldSourceLabel(field: DataArtifactFieldDefinitionViewModel): string {
  if (field.sourceAliases.length === 0) return "—";
  return field.sourceAliases
    .slice(0, 2)
    .map((alias) => `${alias.sourceId} · ${alias.rawField}`)
    .join("；");
}

function FieldDictionaryTable({
  review,
  surface,
}: {
  readonly review: FieldDictionaryArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
}) {
  const fields = review.fieldDefinitions.slice(
    0,
    SURFACE_LIMITS[surface].fields,
  );
  return (
    <div className="data-artifact__table-scroll">
      <table className="data-artifact__table data-artifact__table--dictionary">
        <caption className="sr-only">规范字段定义、单位与来源映射</caption>
        <thead>
          <tr>
            <th scope="col">字段</th>
            <th scope="col">含义</th>
            <th scope="col">类型 / 单位</th>
            <th scope="col">来源映射</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field.fieldId}>
              <th scope="row">{fieldLabel(field)}</th>
              <td>{field.description || "未提供字段描述。"}</td>
              <td>
                {field.dataType}
                {field.canonicalUnit ? ` · ${field.canonicalUnit}` : ""}
                <small>
                  {field.required ? "必填" : "可选"} ·{" "}
                  {field.nullable ? "可为空" : "不可为空"}
                </small>
              </td>
              <td>{fieldSourceLabel(field)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.fieldDefinitions.length > fields.length ? (
        <p className="data-artifact__table-note">
          当前显示前 {fields.length} / {review.fieldDefinitions.length} 个字段。
        </p>
      ) : null}
    </div>
  );
}

function FieldDictionaryRenderer({
  review,
  title,
  surface,
}: {
  readonly review: FieldDictionaryArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
}) {
  return (
    <article
      className="data-artifact data-artifact--field-dictionary"
      data-surface={surface}
    >
      <header className="data-artifact__header">
        <div>
          <h3>{title}</h3>
          <p className="data-artifact__subtitle">
            字段字典 · {review.fieldDefinitions.length} 个字段
          </p>
        </div>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      {review.fieldDefinitions.length > 0 ? (
        <FieldDictionaryTable review={review} surface={surface} />
      ) : (
        <p className="data-artifact__empty">当前版本没有可展示的字段定义。</p>
      )}
    </article>
  );
}

function SourceCollectionTable({
  review,
  surface,
}: {
  readonly review: SourceCollectionArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
}) {
  const members = review.members.slice(0, SURFACE_LIMITS[surface].fields);
  return (
    <div className="data-artifact__table-scroll">
      <table className="data-artifact__table data-artifact__table--sources">
        <caption className="sr-only">数据产物使用的来源与记录数量</caption>
        <thead>
          <tr>
            <th scope="col">来源</th>
            <th scope="col">数据级别</th>
            <th scope="col">记录数量</th>
            <th scope="col">完成状态</th>
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={`${member.sourceSnapshotId}-${member.side}`}>
              <th scope="row">{member.sourceId ?? "未提供来源名称"}</th>
              <td>{member.dataLevel}</td>
              <td>
                {member.rawRecordCount === null ? "—" : member.rawRecordCount}
              </td>
              <td>{member.completionStatus}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.members.length > members.length ? (
        <p className="data-artifact__table-note">
          当前显示前 {members.length} / {review.members.length} 个来源成员。
        </p>
      ) : null}
    </div>
  );
}

function SourceCollectionRenderer({
  review,
  title,
  surface,
}: {
  readonly review: SourceCollectionArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
}) {
  return (
    <article
      className="data-artifact data-artifact--source-collection"
      data-surface={surface}
    >
      <header className="data-artifact__header">
        <div>
          <h3>{title}</h3>
          <p className="data-artifact__subtitle">
            来源集合 · {review.members.length} 个来源成员
          </p>
        </div>
      </header>
      <div className="data-artifact__summary" aria-label="来源集合质量摘要">
        <span>已对齐 {review.alignedRecordCount}</span>
        {review.conflictRecordCount > 0 ? (
          <span>冲突 {review.conflictRecordCount}</span>
        ) : null}
        <span>待核验 {review.reviewRequiredRecordCount}</span>
      </div>
      <ArtifactMetadata review={review} surface={surface} />
      {review.members.length > 0 ? (
        <SourceCollectionTable review={review} surface={surface} />
      ) : (
        <p className="data-artifact__empty">
          当前版本只返回来源快照引用，尚未提供来源成员明细。
        </p>
      )}
    </article>
  );
}

export function DataArtifactRenderer({
  review,
  title,
  surface,
  onSelectEvidence,
}: DataArtifactRendererProps) {
  if (review.kind === "dataset") {
    return (
      <DatasetRenderer
        review={review}
        title={title}
        surface={surface}
        onSelectEvidence={onSelectEvidence}
      />
    );
  }
  if (review.kind === "field_dictionary") {
    return (
      <FieldDictionaryRenderer
        review={review}
        title={title}
        surface={surface}
      />
    );
  }
  return (
    <SourceCollectionRenderer review={review} title={title} surface={surface} />
  );
}
