import { useMemo, useState } from "react";
import type { DomainEntityId } from "@xingwen/domain";
import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";
import { Badge, Input } from "@xingwen/ui";
import { Search } from "@xingwen/ui/icons";

import { ScientificTable } from "./scientific-table";
import { ArtifactMetadataStrip, ArtifactToolbar } from "./result-layout";

export type DataArtifactSurface = "fullscreen";

export interface DataArtifactRendererProps {
  readonly review: DataArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
  readonly showSummary?: boolean;
  readonly enhancementOnly?: boolean;
}

const SURFACE_LIMITS: Record<
  DataArtifactSurface,
  { readonly rows: number; readonly columns: number; readonly fields: number }
> = {
  fullscreen: { rows: 100, columns: 24, fields: 100 },
};

function fieldLabel(field: DataArtifactFieldDefinitionViewModel): string {
  return field.meaningZh || field.labelEn || "未命名字段";
}

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
  return (
    <ScientificTable
      caption="研究数据集中的规范化字段与数据行"
      columns={review.columns.map((column) => ({
        key: String(column.fieldId),
        label: fieldLabel(column),
        unit: column.canonicalUnit || null,
      }))}
      rows={review.rows.map((row) => ({
        id: String(row.rowId),
        identity: row.identity,
        cells: Object.fromEntries(
          row.cells.map((cell) => [
            String(cell.canonicalFieldId),
            {
              value: cell.value,
              unit: cell.unit,
              status: cell.status === "declared_null" ? "missing" : cell.status,
              reason: cell.reason,
              evidenceIds: cell.evidenceIds,
            },
          ]),
        ),
      }))}
      maxRows={limits.rows}
      maxColumns={limits.columns}
      showIdentity
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function DatasetRenderer({
  review,
  title,
  surface,
  onSelectEvidence,
  showSummary = true,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
  readonly showSummary?: boolean;
}) {
  const retrievedAt = review.sourceSnapshots
    .map((snapshot) => snapshot.retrievedAt)
    .sort()
    .at(-1);

  return (
    <article
      className="data-artifact data-artifact--dataset flex flex-col gap-3 min-h-0 flex-1"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header">
          <h3 className="font-serif text-lg font-semibold text-foreground">
            {title}
          </h3>
        </header>
      ) : null}

      <ArtifactMetadataStrip
        sourceCount={review.sourceSnapshots.length}
        retrievedAt={retrievedAt}
        qualityStatus={review.quality.status}
        recordCount={review.rowCount}
        fieldCount={review.fieldCount}
        evidenceCount={review.evidenceIds.length}
        statusBadge={
          review.conflictCount > 0
            ? {
                label: `存在 ${review.conflictCount} 处冲突`,
                variant: "destructive",
              }
            : null
        }
      />

      <div className="min-h-0 flex-1 overflow-auto">
        {review.rows.length > 0 && review.columns.length > 0 ? (
          <DatasetTable
            review={review}
            surface={surface}
            onSelectEvidence={onSelectEvidence}
          />
        ) : (
          <div className="flex flex-col items-center justify-center p-12 text-center text-xs text-muted-foreground">
            当前版本没有可展示的数据行或字段。
          </div>
        )}
      </div>
    </article>
  );
}

function fieldSourceLabel(field: DataArtifactFieldDefinitionViewModel): string {
  return field.sourceAliases.length > 0
    ? `已映射 ${field.sourceAliases.length} 个来源字段`
    : "未提供";
}

function FieldDictionaryRenderer({
  review,
  title,
  surface,
  showSummary = true,
}: {
  readonly review: FieldDictionaryArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly showSummary?: boolean;
}) {
  const [filterQuery, setFilterQuery] = useState("");
  const retrievedAt = review.sourceSnapshots
    .map((snapshot) => snapshot.retrievedAt)
    .sort()
    .at(-1);

  const filteredFields = useMemo(() => {
    const query = filterQuery.trim().toLowerCase();
    if (!query) return review.fieldDefinitions;
    return review.fieldDefinitions.filter(
      (field) =>
        field.labelEn.toLowerCase().includes(query) ||
        field.meaningZh.toLowerCase().includes(query) ||
        field.description.toLowerCase().includes(query) ||
        String(field.fieldId).includes(query),
    );
  }, [review.fieldDefinitions, filterQuery]);

  const displayedFields = filteredFields.slice(
    0,
    SURFACE_LIMITS[surface].fields,
  );

  return (
    <article
      className="data-artifact data-artifact--field-dictionary flex flex-col gap-3 min-h-0 flex-1"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header">
          <h3 className="font-serif text-lg font-semibold text-foreground">
            {title}
          </h3>
        </header>
      ) : null}

      <ArtifactMetadataStrip
        sourceCount={review.sourceSnapshots.length}
        retrievedAt={retrievedAt}
        qualityStatus={review.quality.status}
        fieldCount={review.fieldDefinitions.length}
        evidenceCount={review.evidenceIds.length}
      />

      <ArtifactToolbar
        left={
          <div className="relative min-w-64 max-w-sm">
            <Search
              className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              placeholder="搜索字段名称、含义或标识…"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="h-8 pl-8 text-xs"
            />
          </div>
        }
        right={
          <span className="text-xs text-muted-foreground">
            共 {filteredFields.length} 个字段定义
          </span>
        }
      />

      <div className="min-h-0 flex-1 overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full text-left text-xs border-collapse">
          <caption className="sr-only">规范字段定义、单位与来源映射</caption>
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th scope="col" className="p-2.5 font-medium text-foreground">
                字段标识 / 名称
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                中文含义与描述
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                类型 / 单位 / 约束
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                来源字段映射
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {displayedFields.map((field) => (
              <tr
                key={field.fieldId}
                className="transition-colors hover:bg-surface-hover/50"
              >
                <th
                  scope="row"
                  className="p-2.5 font-normal text-foreground align-top"
                >
                  <div className="font-medium text-foreground">
                    {fieldLabel(field)}
                  </div>
                  <div className="font-mono text-[11px] text-muted-foreground">
                    {field.labelEn || field.fieldId}
                  </div>
                </th>
                <td className="p-2.5 text-muted-foreground align-top max-w-xs">
                  <p className="line-clamp-2">
                    {field.description || field.meaningZh || "未提供字段描述。"}
                  </p>
                </td>
                <td className="p-2.5 text-foreground align-top">
                  <div className="font-mono text-xs">
                    {field.dataType}
                    {field.canonicalUnit ? ` · ${field.canonicalUnit}` : ""}
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Badge
                      variant={field.required ? "secondary" : "outline"}
                      className="h-4 px-1 text-[10px]"
                    >
                      {field.required ? "必填" : "可选"}
                    </Badge>
                    <span>{field.nullable ? "可空" : "非空"}</span>
                  </div>
                </td>
                <td className="p-2.5 text-muted-foreground align-top font-mono text-[11px]">
                  {fieldSourceLabel(field)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredFields.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            没有匹配的字段定义。
          </div>
        ) : null}
      </div>
    </article>
  );
}

function SourceCollectionRenderer({
  review,
  title,
  surface,
  showSummary = true,
}: {
  readonly review: SourceCollectionArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly showSummary?: boolean;
}) {
  const retrievedAt = review.sourceSnapshots
    .map((snapshot) => snapshot.retrievedAt)
    .sort()
    .at(-1);

  const members = review.members.slice(0, SURFACE_LIMITS[surface].fields);

  return (
    <article
      className="data-artifact data-artifact--source-collection flex flex-col gap-3 min-h-0 flex-1"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header">
          <h3 className="font-serif text-lg font-semibold text-foreground">
            {title}
          </h3>
        </header>
      ) : null}

      <ArtifactMetadataStrip
        sourceCount={review.members.length}
        retrievedAt={retrievedAt}
        qualityStatus={review.quality.status}
        recordCount={review.alignedRecordCount}
        evidenceCount={review.evidenceIds.length}
        statusBadge={
          review.conflictRecordCount > 0
            ? {
                label: `冲突 ${review.conflictRecordCount} 项`,
                variant: "destructive",
              }
            : null
        }
      />

      <div className="min-h-0 flex-1 overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full text-left text-xs border-collapse">
          <caption className="sr-only">数据产物使用的来源与记录数量</caption>
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th scope="col" className="p-2.5 font-medium text-foreground">
                来源名称 / 标识
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                数据级别
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                记录数量
              </th>
              <th scope="col" className="p-2.5 font-medium text-foreground">
                处理状态
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {members.map((member) => (
              <tr
                key={`${member.sourceSnapshotId}-${member.side}`}
                className="transition-colors hover:bg-surface-hover/50"
              >
                <th scope="row" className="p-2.5 font-medium text-foreground">
                  {member.sourceId ?? "未提供来源名称"}
                </th>
                <td className="p-2.5 text-muted-foreground">
                  <Badge variant="outline" className="h-4 px-1 text-[10px]">
                    {member.dataLevel}
                  </Badge>
                </td>
                <td className="p-2.5 font-mono text-foreground">
                  {member.rawRecordCount === null
                    ? "—"
                    : `${member.rawRecordCount} 条`}
                </td>
                <td className="p-2.5 text-muted-foreground">
                  <Badge
                    variant={
                      member.completionStatus === "completed"
                        ? "secondary"
                        : "outline"
                    }
                    className="h-4 px-1 text-[10px]"
                  >
                    {member.completionStatus === "completed"
                      ? "已完成"
                      : member.completionStatus}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {members.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            当前版本只返回来源快照引用，尚未提供来源成员明细。
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function DataArtifactRenderer({
  review,
  title,
  surface,
  onSelectEvidence,
  showSummary = true,
}: DataArtifactRendererProps) {
  if (review.kind === "dataset") {
    return (
      <DatasetRenderer
        review={review}
        title={title}
        surface={surface}
        onSelectEvidence={onSelectEvidence}
        showSummary={showSummary}
      />
    );
  }
  if (review.kind === "field_dictionary") {
    return (
      <FieldDictionaryRenderer
        review={review}
        title={title}
        surface={surface}
        showSummary={showSummary}
      />
    );
  }
  return (
    <SourceCollectionRenderer
      review={review}
      title={title}
      surface={surface}
      showSummary={showSummary}
    />
  );
}
