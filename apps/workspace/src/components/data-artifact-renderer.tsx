import type { DomainEntityId } from "@xingwen/domain";
import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  DatasetCellReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@xingwen/ui";
import { useMemo, useState } from "react";

export type DataArtifactSurface = "fullscreen";

export interface DataArtifactRendererProps {
  readonly review: DataArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
}

const SURFACE_LIMITS: Record<
  DataArtifactSurface,
  { readonly rows: number; readonly columns: number; readonly fields: number }
> = {
  fullscreen: { rows: 100, columns: 24, fields: 100 },
};

function displayValue(value: string | null): string {
  return value === null || value.trim() === "" ? "—" : value;
}

function sourceModeLabel(mode: string): string {
  if (mode === "live") return "实时数据";
  if (mode === "cached") return "缓存数据";
  if (mode === "fixture") return "演示数据";
  return "来源状态未知";
}

function fieldLabel(field: DataArtifactFieldDefinitionViewModel): string {
  return field.meaningZh || field.labelEn || "未命名字段";
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
    <dl className="data-artifact__metadata flex flex-wrap gap-4 text-xs text-[var(--oh-muted)] my-2">
      <div>
        <dt className="inline font-medium">来源模式：</dt>
        <dd className="inline">{sourceModeLabel(review.sourceMode)}</dd>
      </div>
      <div>
        <dt className="inline font-medium">来源：</dt>
        <dd className="inline">
          {review.sourceSnapshots.length > 0
            ? `已记录 ${review.sourceSnapshots.length} 个来源快照`
            : "未提供"}
        </dd>
      </div>
      {retrievedAt ? (
        <div>
          <dt className="inline font-medium">获取时间：</dt>
          <dd className="inline">{retrievedAt}</dd>
        </div>
      ) : null}
      <div>
        <dt className="inline font-medium">质量状态：</dt>
        <dd className="inline">
          {review.quality.status === "pass" ? "已校验" : "质量状态未知"}
        </dd>
      </div>
      {surface === "fullscreen" && review.evidenceIds.length > 0 ? (
        <div>
          <dt className="inline font-medium">关联证据：</dt>
          <dd className="inline">{review.evidenceIds.length} 条</dd>
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
          <small className="text-xs text-[var(--oh-muted)]"> {cell.unit}</small>
        ) : null}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant={cell.status === "unresolved" ? "destructive" : "outline"}>
        {cell.status === "unresolved" ? "未解析" : "空值"}
      </Badge>
      {cell.reason ? (
        <small className="text-xs text-[var(--oh-muted)]">{cell.reason}</small>
      ) : null}
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
  const allColumns = review.columns.slice(0, limits.columns);
  const [hiddenFields, setHiddenFields] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [sort, setSort] = useState<{
    field: string;
    direction: SortDirection;
  } | null>(null);

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
    <div className="data-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--oh-border)]">
      <div className="flex justify-end border-b border-[var(--oh-border)] bg-[var(--oh-surface-subtle)] p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="small" variant="ghost">
              选择列
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-72 overflow-y-auto">
            {allColumns.map((column) => {
              const fieldId = String(column.fieldId);
              return (
                <DropdownMenuCheckboxItem
                  key={column.fieldId}
                  checked={!hiddenFields.has(fieldId)}
                  onCheckedChange={() => toggleColumn(fieldId)}
                >
                  {fieldLabel(column)}
                </DropdownMenuCheckboxItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <table className="w-full text-[13px] text-left border-collapse">
        <caption className="sr-only">研究数据集中的规范化字段与数据行</caption>
        <thead>
          <tr className="border-b bg-[var(--oh-surface-subtle)] border-[var(--oh-border)]">
            <th scope="col" className="p-2 font-medium">
              标识 / 主体
            </th>
            {columns.map((column) => (
              <th scope="col" key={column.fieldId} className="p-2 font-medium">
                <Button
                  variant="ghost"
                  size="small"
                  className="h-auto p-0 font-medium text-[13px] text-inherit"
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
        <tbody className="divide-y divide-[var(--oh-border)]">
          {rows.map((row) => {
            const cells = new Map(
              row.cells.map((cell) => [String(cell.canonicalFieldId), cell]),
            );
            return (
              <tr
                key={row.rowId}
                className="hover:bg-[var(--oh-surface-subtle)]"
              >
                <th
                  scope="row"
                  className="p-2 font-normal text-[var(--oh-muted)]"
                  title={row.identity || undefined}
                >
                  {row.identity || "未命名记录"}
                </th>
                {columns.map((column) => {
                  const cell = cells.get(String(column.fieldId));
                  return (
                    <td key={column.fieldId} className="p-2">
                      {cell ? (
                        cell.evidenceIds.length > 0 && onSelectEvidence ? (
                          <Button
                            variant="ghost"
                            size="small"
                            className="h-auto p-0 text-inherit text-[13px]"
                            title="查看该数值的证据"
                            onClick={() => onSelectEvidence(cell.evidenceIds)}
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
        <p className="p-2 text-xs text-[var(--oh-muted)] bg-[var(--oh-surface-subtle)] border-t border-[var(--oh-border)]">
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
      <header className="data-artifact__header mb-2">
        <h3 className="text-sm font-semibold text-[var(--oh-foreground)]">
          {title}
        </h3>
        <p className="text-xs text-[var(--oh-muted)] mt-0.5">
          数据表 · {review.rowCount} 行 · {review.fieldCount} 个字段
          {review.conflictCount > 0 ? ` · 冲突 ${review.conflictCount}` : ""}
        </p>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      {review.rows.length > 0 && review.columns.length > 0 ? (
        <DatasetTable
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <p className="text-xs text-[var(--oh-muted)] py-4 text-center">
          当前版本没有可展示的数据行或字段。
        </p>
      )}
    </article>
  );
}

function fieldSourceLabel(field: DataArtifactFieldDefinitionViewModel): string {
  return field.sourceAliases.length > 0
    ? `已映射 ${field.sourceAliases.length} 个来源字段`
    : "未提供";
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
    <div className="data-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--oh-border)]">
      <table className="w-full text-[13px] text-left border-collapse">
        <caption className="sr-only">规范字段定义、单位与来源映射</caption>
        <thead>
          <tr className="border-b bg-[var(--oh-surface-subtle)] border-[var(--oh-border)]">
            <th scope="col" className="p-2 font-medium">
              字段
            </th>
            <th scope="col" className="p-2 font-medium">
              含义
            </th>
            <th scope="col" className="p-2 font-medium">
              类型 / 单位
            </th>
            <th scope="col" className="p-2 font-medium">
              来源映射
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {fields.map((field) => (
            <tr
              key={field.fieldId}
              className="hover:bg-[var(--oh-surface-subtle)]"
            >
              <th
                scope="row"
                className="p-2 font-medium text-[var(--oh-foreground)]"
              >
                {fieldLabel(field)}
              </th>
              <td className="p-2 text-[var(--oh-muted)]">
                {field.description || "未提供字段描述。"}
              </td>
              <td className="p-2">
                {field.dataType}
                {field.canonicalUnit ? ` · ${field.canonicalUnit}` : ""}
                <div className="text-[10px] text-[var(--oh-muted)] mt-0.5">
                  {field.required ? "必填" : "可选"} ·{" "}
                  {field.nullable ? "可为空" : "不可为空"}
                </div>
              </td>
              <td className="p-2 text-[var(--oh-muted)]">
                {fieldSourceLabel(field)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.fieldDefinitions.length > fields.length ? (
        <p className="p-2 text-xs text-[var(--oh-muted)] bg-[var(--oh-surface-subtle)] border-t border-[var(--oh-border)]">
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
      <header className="data-artifact__header mb-2">
        <h3 className="text-sm font-semibold text-[var(--oh-foreground)]">
          {title}
        </h3>
        <p className="text-xs text-[var(--oh-muted)] mt-0.5">
          字段字典 · {review.fieldDefinitions.length} 个字段
        </p>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      {review.fieldDefinitions.length > 0 ? (
        <FieldDictionaryTable review={review} surface={surface} />
      ) : (
        <p className="text-xs text-[var(--oh-muted)] py-4 text-center">
          当前版本没有可展示的字段定义。
        </p>
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
    <div className="data-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--oh-border)]">
      <table className="w-full text-[13px] text-left border-collapse">
        <caption className="sr-only">数据产物使用的来源与记录数量</caption>
        <thead>
          <tr className="border-b bg-[var(--oh-surface-subtle)] border-[var(--oh-border)]">
            <th scope="col" className="p-2 font-medium">
              来源
            </th>
            <th scope="col" className="p-2 font-medium">
              数据级别
            </th>
            <th scope="col" className="p-2 font-medium">
              记录数量
            </th>
            <th scope="col" className="p-2 font-medium">
              完成状态
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {members.map((member) => (
            <tr
              key={`${member.sourceSnapshotId}-${member.side}`}
              className="hover:bg-[var(--oh-surface-subtle)]"
            >
              <th
                scope="row"
                className="p-2 font-medium text-[var(--oh-foreground)]"
              >
                {member.sourceId ?? "未提供来源名称"}
              </th>
              <td className="p-2 text-[var(--oh-muted)]">{member.dataLevel}</td>
              <td className="p-2">
                {member.rawRecordCount === null ? "—" : member.rawRecordCount}
              </td>
              <td className="p-2 text-[var(--oh-muted)]">
                {member.completionStatus}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.members.length > members.length ? (
        <p className="p-2 text-xs text-[var(--oh-muted)] bg-[var(--oh-surface-subtle)] border-t border-[var(--oh-border)]">
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
      <header className="data-artifact__header mb-2">
        <h3 className="text-sm font-semibold text-[var(--oh-foreground)]">
          {title}
        </h3>
        <p className="text-xs text-[var(--oh-muted)] mt-0.5">
          来源集合 · {review.members.length} 个来源成员
        </p>
      </header>
      <div
        className="data-artifact__summary flex flex-wrap gap-3 text-xs text-[var(--oh-muted)] my-1.5 p-2 bg-[var(--oh-surface-subtle)] rounded"
        aria-label="来源集合质量摘要"
      >
        <span>已对齐 {review.alignedRecordCount} 项</span>
        {review.conflictRecordCount > 0 ? (
          <span className="text-[var(--oh-danger)]">
            冲突 {review.conflictRecordCount} 项
          </span>
        ) : null}
        <span>待核验 {review.reviewRequiredRecordCount} 项</span>
      </div>
      <ArtifactMetadata review={review} surface={surface} />
      {review.members.length > 0 ? (
        <SourceCollectionTable review={review} surface={surface} />
      ) : (
        <p className="text-xs text-[var(--oh-muted)] py-4 text-center">
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
