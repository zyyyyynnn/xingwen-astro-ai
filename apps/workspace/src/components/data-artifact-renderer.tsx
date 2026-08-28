import type { DomainEntityId } from "@xingwen/domain";
import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";

import { ScientificTable } from "./scientific-table";

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
    <dl className="data-artifact__metadata flex flex-wrap gap-4 text-xs text-[var(--color-ink-secondary)] my-2">
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
  enhancementOnly = false,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly onSelectEvidence?: (evidenceIds: readonly DomainEntityId[]) => void;
  readonly showSummary?: boolean;
  readonly enhancementOnly?: boolean;
}) {
  if (enhancementOnly) {
    return <ArtifactMetadata review={review} surface={surface} />;
  }
  return (
    <article
      className="data-artifact data-artifact--dataset"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header mb-2">
          <h3 className="text-sm font-semibold text-[var(--color-ink-primary)]">
            {title}
          </h3>
          <p className="text-xs text-[var(--color-ink-secondary)] mt-0.5">
            数据表 · {review.rowCount} 行 · {review.fieldCount} 个字段
            {review.conflictCount > 0 ? ` · 冲突 ${review.conflictCount}` : ""}
          </p>
        </header>
      ) : null}
      <ArtifactMetadata review={review} surface={surface} />
      {review.rows.length > 0 && review.columns.length > 0 ? (
        <DatasetTable
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <p className="text-xs text-[var(--color-ink-secondary)] py-4 text-center">
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
    <div className="data-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--color-border)]">
      <table className="ui-text-body w-full text-left border-collapse">
        <caption className="sr-only">规范字段定义、单位与来源映射</caption>
        <thead>
          <tr className="border-b bg-[var(--color-surface-muted)] border-[var(--color-border)]">
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
        <tbody className="divide-y divide-[var(--color-border)]">
          {fields.map((field) => (
            <tr
              key={field.fieldId}
              className="hover:bg-[var(--color-surface-muted)]"
            >
              <th
                scope="row"
                className="p-2 font-medium text-[var(--color-ink-primary)]"
              >
                {fieldLabel(field)}
              </th>
              <td className="p-2 text-[var(--color-ink-secondary)]">
                {field.description || "未提供字段描述。"}
              </td>
              <td className="p-2">
                {field.dataType}
                {field.canonicalUnit ? ` · ${field.canonicalUnit}` : ""}
                <div className="ui-text-label mt-0.5 text-[var(--color-ink-secondary)]">
                  {field.required ? "必填" : "可选"} ·{" "}
                  {field.nullable ? "可为空" : "不可为空"}
                </div>
              </td>
              <td className="p-2 text-[var(--color-ink-secondary)]">
                {fieldSourceLabel(field)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.fieldDefinitions.length > fields.length ? (
        <p className="p-2 text-xs text-[var(--color-ink-secondary)] bg-[var(--color-surface-muted)] border-t border-[var(--color-border)]">
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
  showSummary = true,
}: {
  readonly review: FieldDictionaryArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly showSummary?: boolean;
}) {
  return (
    <article
      className="data-artifact data-artifact--field-dictionary"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header mb-2">
          <h3 className="text-sm font-semibold text-[var(--color-ink-primary)]">
            {title}
          </h3>
          <p className="text-xs text-[var(--color-ink-secondary)] mt-0.5">
            字段字典 · {review.fieldDefinitions.length} 个字段
          </p>
        </header>
      ) : null}
      <ArtifactMetadata review={review} surface={surface} />
      {review.fieldDefinitions.length > 0 ? (
        <FieldDictionaryTable review={review} surface={surface} />
      ) : (
        <p className="text-xs text-[var(--color-ink-secondary)] py-4 text-center">
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
    <div className="data-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--color-border)]">
      <table className="ui-text-body w-full text-left border-collapse">
        <caption className="sr-only">数据产物使用的来源与记录数量</caption>
        <thead>
          <tr className="border-b bg-[var(--color-surface-muted)] border-[var(--color-border)]">
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
        <tbody className="divide-y divide-[var(--color-border)]">
          {members.map((member) => (
            <tr
              key={`${member.sourceSnapshotId}-${member.side}`}
              className="hover:bg-[var(--color-surface-muted)]"
            >
              <th
                scope="row"
                className="p-2 font-medium text-[var(--color-ink-primary)]"
              >
                {member.sourceId ?? "未提供来源名称"}
              </th>
              <td className="p-2 text-[var(--color-ink-secondary)]">
                {member.dataLevel}
              </td>
              <td className="p-2">
                {member.rawRecordCount === null ? "—" : member.rawRecordCount}
              </td>
              <td className="p-2 text-[var(--color-ink-secondary)]">
                {member.completionStatus}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {review.members.length > members.length ? (
        <p className="p-2 text-xs text-[var(--color-ink-secondary)] bg-[var(--color-surface-muted)] border-t border-[var(--color-border)]">
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
  showSummary = true,
}: {
  readonly review: SourceCollectionArtifactReviewViewModel;
  readonly title: string;
  readonly surface: DataArtifactSurface;
  readonly showSummary?: boolean;
}) {
  return (
    <article
      className="data-artifact data-artifact--source-collection"
      data-surface={surface}
    >
      {showSummary ? (
        <header className="data-artifact__header mb-2">
          <h3 className="text-sm font-semibold text-[var(--color-ink-primary)]">
            {title}
          </h3>
          <p className="text-xs text-[var(--color-ink-secondary)] mt-0.5">
            来源集合 · {review.members.length} 个来源成员
          </p>
        </header>
      ) : null}
      <div
        className="data-artifact__summary flex flex-wrap gap-3 text-xs text-[var(--color-ink-secondary)] my-1.5 p-2 bg-[var(--color-surface-muted)] rounded"
        aria-label="来源集合质量摘要"
      >
        <span>已对齐 {review.alignedRecordCount} 项</span>
        {review.conflictRecordCount > 0 ? (
          <span className="text-[var(--color-error)]">
            冲突 {review.conflictRecordCount} 项
          </span>
        ) : null}
        <span>待核验 {review.reviewRequiredRecordCount} 项</span>
      </div>
      <ArtifactMetadata review={review} surface={surface} />
      {review.members.length > 0 ? (
        <SourceCollectionTable review={review} surface={surface} />
      ) : (
        <p className="text-xs text-[var(--color-ink-secondary)] py-4 text-center">
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
  showSummary = true,
  enhancementOnly = false,
}: DataArtifactRendererProps) {
  if (review.kind === "dataset") {
    return (
      <DatasetRenderer
        review={review}
        title={title}
        surface={surface}
        onSelectEvidence={onSelectEvidence}
        showSummary={showSummary}
        enhancementOnly={enhancementOnly}
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
