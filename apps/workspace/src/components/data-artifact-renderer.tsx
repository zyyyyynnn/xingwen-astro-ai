import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  DatasetCellReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";
import { Badge, Separator } from "@xingwen/ui";

export type DataArtifactSurface = "thread" | "docked" | "fullscreen";

export interface DataArtifactRendererProps {
  readonly review: DataArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: DataArtifactSurface;
}

const SURFACE_LIMITS: Record<
  DataArtifactSurface,
  { readonly rows: number; readonly columns: number; readonly fields: number }
> = {
  thread: { rows: 4, columns: 6, fields: 4 },
  docked: { rows: 40, columns: 16, fields: 40 },
  fullscreen: { rows: 100, columns: 24, fields: 100 },
};

function displayValue(value: string | null): string {
  return value === null || value.trim() === "" ? "—" : value;
}

function sourceModeLabel(mode: string): string {
  if (mode === "live") return "实时数据";
  if (mode === "cached") return "缓存数据";
  return "演示数据";
}

function ArtifactMetadata({
  review,
  surface,
}: {
  readonly review: DataArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
}) {
  return (
    <dl className="data-artifact__metadata">
      <div>
        <dt>来源模式</dt>
        <dd>{sourceModeLabel(review.sourceMode)}</dd>
      </div>
      <div>
        <dt>版本</dt>
        <dd>v{review.schemaVersion}</dd>
      </div>
      <div>
        <dt>来源快照</dt>
        <dd>{review.sourceSnapshots.length}</dd>
      </div>
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

function DatasetTable({
  review,
  surface,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly surface: DataArtifactSurface;
}) {
  const limits = SURFACE_LIMITS[surface];
  const columns = review.columns.slice(0, limits.columns);
  const visibleRows = review.rows.slice(0, limits.rows);
  return (
    <div className="data-artifact__table-scroll">
      <table className="data-artifact__table">
        <caption className="sr-only">研究数据集中的规范化字段与数据行</caption>
        <thead>
          <tr>
            <th scope="col">行</th>
            {columns.map((column) => (
              <th scope="col" key={column.fieldId}>
                <span>
                  {column.meaningZh || column.labelEn || column.fieldId}
                </span>
                <small>{column.fieldId}</small>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row) => {
            const cells = new Map(
              row.cells.map((cell) => [String(cell.canonicalFieldId), cell]),
            );
            return (
              <tr key={row.rowId}>
                <th scope="row" title={row.identity || undefined}>
                  {row.identity || row.rowId}
                </th>
                {columns.map((column) => {
                  const cell = cells.get(String(column.fieldId));
                  return (
                    <td key={column.fieldId}>
                      {cell ? <CellValue cell={cell} /> : "—"}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {review.rows.length > visibleRows.length ? (
        <p className="data-artifact__table-note">
          当前显示前 {visibleRows.length} / {review.rowCount} 行。
        </p>
      ) : null}
    </div>
  );
}

function DatasetRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: DatasetArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: DataArtifactSurface;
}) {
  return (
    <article
      className="data-artifact data-artifact--dataset"
      data-surface={surface}
    >
      <header className="data-artifact__header">
        <div>
          <h3>{title}</h3>
          <p>数据表 · v{versionNumber}</p>
        </div>
        <div className="data-artifact__badges">
          <Badge variant="outline">{review.rowCount} 行</Badge>
          <Badge variant="outline">{review.fieldCount} 个字段</Badge>
          {review.conflictCount > 0 ? (
            <Badge variant="destructive">冲突 {review.conflictCount}</Badge>
          ) : null}
        </div>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      <Separator />
      {review.rows.length > 0 && review.columns.length > 0 ? (
        <DatasetTable review={review} surface={surface} />
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
              <th scope="row">
                <span>{field.meaningZh || field.labelEn || field.fieldId}</span>
                <small>{field.fieldId}</small>
              </th>
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
  versionNumber,
  surface,
}: {
  readonly review: FieldDictionaryArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
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
          <p>字段字典 · v{versionNumber}</p>
        </div>
        <Badge variant="outline">{review.fieldDefinitions.length} 个字段</Badge>
      </header>
      <ArtifactMetadata review={review} surface={surface} />
      <Separator />
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
        <caption className="sr-only">数据产物使用的来源快照与来源记录</caption>
        <thead>
          <tr>
            <th scope="col">来源</th>
            <th scope="col">侧 / 数据级别</th>
            <th scope="col">快照</th>
            <th scope="col">原始记录</th>
            <th scope="col">完成状态</th>
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={`${member.sourceSnapshotId}-${member.side}`}>
              <th scope="row">{member.sourceId ?? "未提供来源 ID"}</th>
              <td>
                {member.side} · {member.dataLevel}
              </td>
              <td>
                <span>{member.sourceSnapshotId}</span>
                {member.sourceSnapshotContentHash ? (
                  <small>{member.sourceSnapshotContentHash}</small>
                ) : null}
              </td>
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
  versionNumber,
  surface,
}: {
  readonly review: SourceCollectionArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
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
          <p>来源集合 · v{versionNumber}</p>
        </div>
        <Badge variant="outline">{review.members.length} 个来源成员</Badge>
      </header>
      <div className="data-artifact__summary" aria-label="来源集合质量摘要">
        <span>已对齐 {review.alignedRecordCount}</span>
        <span>冲突 {review.conflictRecordCount}</span>
        <span>待核验 {review.reviewRequiredRecordCount}</span>
      </div>
      <ArtifactMetadata review={review} surface={surface} />
      <Separator />
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
  versionNumber,
  surface,
}: DataArtifactRendererProps) {
  if (review.kind === "dataset") {
    return (
      <DatasetRenderer
        review={review}
        title={title}
        versionNumber={versionNumber}
        surface={surface}
      />
    );
  }
  if (review.kind === "field_dictionary") {
    return (
      <FieldDictionaryRenderer
        review={review}
        title={title}
        versionNumber={versionNumber}
        surface={surface}
      />
    );
  }
  return (
    <SourceCollectionRenderer
      review={review}
      title={title}
      versionNumber={versionNumber}
      surface={surface}
    />
  );
}
