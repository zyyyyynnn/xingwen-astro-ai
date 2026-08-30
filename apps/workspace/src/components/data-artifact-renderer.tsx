import { useMemo, useState } from "react";
import type { DomainEntityId } from "@xingwen/domain";
import type {
  DataArtifactFieldDefinitionViewModel,
  DataArtifactReviewViewModel,
  DatasetArtifactReviewViewModel,
  FieldDictionaryArtifactReviewViewModel,
  SourceCollectionArtifactReviewViewModel,
} from "@xingwen/research-adapter";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Input,
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@xingwen/ui";
import {
  Database,
  Library,
  Search,
  SearchCheck,
  ShieldCheck,
} from "@xingwen/ui/icons";

import { formatScientificUnit, ScientificTable } from "./scientific-table";
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

function recordIdentity(value: string): string {
  const separator = value.lastIndexOf("=");
  return separator >= 0 ? value.slice(separator + 1).trim() : value;
}

const SOURCE_LABELS: Readonly<Record<string, string>> = {
  "nasa_exoplanet_archive.toi": "NASA Exoplanet Archive · TOI 目录",
  "nasa_exoplanet_archive.ps": "NASA Exoplanet Archive · 行星系统目录",
  "nasa_exoplanet_archive.pscomppars":
    "NASA Exoplanet Archive · 行星系统综合参数",
  gaia_dr3: "Gaia DR3",
  simbad: "SIMBAD 天体数据库",
};

function sourceLabel(sourceId: string | null): string {
  if (!sourceId) return "未提供来源名称";
  return SOURCE_LABELS[sourceId] ?? sourceId.replaceAll("_", " ");
}

const DATA_LEVEL_LABELS: Readonly<Record<string, string>> = {
  fixture: "演示数据",
  seed: "种子数据",
  live: "实时来源",
  live_result: "实时结果",
  cached: "缓存来源",
  recorded: "录制来源",
  recorded_response: "录制响应",
};

const COMPLETION_LABELS: Readonly<Record<string, string>> = {
  complete: "已完成",
  completed: "已完成",
  partial: "部分完成",
  pending: "待处理",
  failed: "处理失败",
  skipped: "已跳过",
};

const DATA_TYPE_LABELS: Readonly<Record<string, string>> = {
  string: "文本",
  number: "数值",
  integer: "整数",
  boolean: "布尔值",
  datetime: "日期时间",
};

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
  const visibleColumns = review.columns.filter((column) => {
    if (review.rows.length === 0) return true;
    return !review.rows.every((row) => {
      const identity = recordIdentity(row.identity);
      const cell = row.cells.find(
        (candidate) => candidate.canonicalFieldId === column.fieldId,
      );
      return identity !== "" && String(cell?.value ?? "") === identity;
    });
  });
  return (
    <ScientificTable
      caption="研究数据集中的规范化字段与数据行"
      columns={visibleColumns.map((column) => ({
        key: String(column.fieldId),
        label: fieldLabel(column),
        unit: column.canonicalUnit || null,
        variant: column.canonicalUnit
          ? ("numeric" as const)
          : column.fieldId === "star_name" ||
              column.fieldId === "host_star_name"
            ? ("identity" as const)
            : undefined,
      }))}
      rows={review.rows.map((row) => ({
        id: String(row.rowId),
        identity: recordIdentity(row.identity),
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
        sourceMode={review.sourceMode}
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

function fieldRoleLabels(
  field: DataArtifactFieldDefinitionViewModel,
): readonly string[] {
  return [
    ...(field.objectIdentityKey ? ["对象标识"] : []),
    ...(field.crossmatchKey ? ["交叉匹配键"] : []),
  ];
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
        sourceMode={review.sourceMode}
        retrievedAt={retrievedAt}
        qualityStatus={review.quality.status}
        fieldCount={review.fieldDefinitions.length}
        evidenceCount={review.evidenceIds.length}
      />

      <ArtifactToolbar
        left={
          <div className="field-dictionary__search relative min-w-64 max-w-sm">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-[var(--icon-size-sm)] -translate-y-1/2 text-muted-foreground"
              data-testid="field-dictionary-search-icon"
              aria-hidden="true"
            />
            <Input
              type="search"
              placeholder="搜索字段名称、含义或标识…"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="field-dictionary__search-input h-8 text-xs"
            />
          </div>
        }
        right={
          <span className="text-xs text-muted-foreground">
            共 {filteredFields.length} 个字段定义
          </span>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        {displayedFields.length > 0 ? (
          <Accordion
            type="multiple"
            defaultValue={
              displayedFields[0] ? [String(displayedFields[0].fieldId)] : []
            }
            className="field-dictionary__list"
          >
            {displayedFields.map((field) => {
              const unit = formatScientificUnit(field.canonicalUnit);
              const roles = fieldRoleLabels(field);
              return (
                <AccordionItem
                  key={field.fieldId}
                  value={String(field.fieldId)}
                  className="field-dictionary__item"
                >
                  <AccordionTrigger className="field-dictionary__trigger">
                    <span className="field-dictionary__identity">
                      <span className="field-dictionary__name">
                        {fieldLabel(field)}
                      </span>
                      <span className="field-dictionary__english">
                        {field.labelEn || "标准字段"}
                      </span>
                    </span>
                    <span className="field-dictionary__traits">
                      {[
                        ...roles,
                        `${DATA_TYPE_LABELS[field.dataType] ?? field.dataType}${unit ? ` · ${unit}` : ""}`,
                        field.required ? "必填" : "可选",
                      ].join(" · ")}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="field-dictionary__content">
                    <p className="field-dictionary__description">
                      {field.description ||
                        field.meaningZh ||
                        "未提供字段描述。"}
                    </p>
                    <dl className="field-dictionary__facts">
                      <div>
                        <dt>空值约束</dt>
                        <dd>{field.nullable ? "允许空值" : "必须提供值"}</dd>
                      </div>
                      <div>
                        <dt>来源映射</dt>
                        <dd>{fieldSourceLabel(field)}</dd>
                      </div>
                      <div>
                        <dt>适用对象</dt>
                        <dd>{field.objectType.replaceAll("_", " ")}</dd>
                      </div>
                    </dl>
                    {field.sourceAliases.length > 0 ? (
                      <div className="field-dictionary__aliases">
                        {field.sourceAliases.map((alias) => (
                          <span
                            key={`${alias.sourceId}:${alias.sourceTable}:${alias.rawField}`}
                          >
                            {sourceLabel(alias.sourceId)} · {alias.rawField}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        ) : (
          <Empty className="border-0 bg-surface-muted/50 py-12">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Search aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle>没有匹配的字段</EmptyTitle>
              <EmptyDescription>
                尝试搜索中文含义、英文名称或标准字段标识。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
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
  const mixesRecordedAndFixtureSources =
    review.members.some((member) => member.sourceMode === "recorded") &&
    review.members.some((member) => member.sourceMode === "fixture");

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
        sourceMode={review.sourceMode}
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

      <dl className="source-collection__metrics">
        <div>
          <dt>已对齐记录</dt>
          <dd>{review.alignedRecordCount}</dd>
        </div>
        <div>
          <dt>待人工审查</dt>
          <dd>{review.reviewRequiredRecordCount}</dd>
        </div>
        <div>
          <dt>不确定匹配</dt>
          <dd>{review.inconclusiveRecordCount}</dd>
        </div>
        <div
          data-state={review.conflictRecordCount > 0 ? "attention" : "clear"}
        >
          <dt>来源冲突</dt>
          <dd>{review.conflictRecordCount}</dd>
        </div>
      </dl>

      {mixesRecordedAndFixtureSources ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          差异统计来自参与对齐的录制响应；标记为演示数据的来源只覆盖接入结构，不计入科研比较。
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {members.length > 0 ? (
          <ItemGroup className="source-collection__grid">
            {members.map((member) => {
              const complete = ["complete", "completed"].includes(
                member.completionStatus ?? "",
              );
              const role =
                member.side === "left"
                  ? "主目录"
                  : member.side === "right"
                    ? "交叉核验"
                    : "研究来源";
              const SourceIcon =
                member.side === "left"
                  ? Database
                  : member.side === "right"
                    ? SearchCheck
                    : Library;
              return (
                <Item
                  key={`${member.sourceSnapshotId}-${member.side}`}
                  variant="default"
                  className="source-collection__item"
                >
                  <ItemMedia
                    className="source-collection__item-icon"
                    data-role={member.side ?? "source"}
                  >
                    <SourceIcon aria-hidden="true" />
                  </ItemMedia>
                  <ItemContent>
                    <div className="source-collection__item-meta">
                      <span>{role}</span>
                      <Badge variant={complete ? "secondary" : "outline"}>
                        {member.completionStatus
                          ? (COMPLETION_LABELS[member.completionStatus] ??
                            "状态未知")
                          : "状态未知"}
                      </Badge>
                    </div>
                    <ItemTitle>{sourceLabel(member.sourceId)}</ItemTitle>
                    <ItemDescription>
                      {member.licenseNote || "来源许可信息未提供。"}
                    </ItemDescription>
                    <div className="source-collection__item-facts">
                      <span>
                        {member.rawRecordCount === null
                          ? "记录数未提供"
                          : `${member.rawRecordCount} 条原始记录`}
                      </span>
                      <span>
                        {member.dataLevel
                          ? (DATA_LEVEL_LABELS[member.dataLevel] ?? "来源数据")
                          : "来源数据"}
                      </span>
                    </div>
                  </ItemContent>
                </Item>
              );
            })}
          </ItemGroup>
        ) : (
          <Empty className="border-0 bg-surface-muted/50 py-12">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Database aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle>来源成员尚未展开</EmptyTitle>
              <EmptyDescription>
                当前版本只返回来源快照引用，尚未提供来源成员明细。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>

      <div className="source-collection__assurance">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>版本化来源闭包已建立</strong>
          <span>每个目录都绑定到本次研究使用的不可变来源快照。</span>
        </div>
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
