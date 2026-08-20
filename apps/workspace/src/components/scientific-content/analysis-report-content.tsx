import type {
  AnalysisReportReviewContent,
  DomainEntityId,
  ScientificMetricReview,
  ScientificResultBlockReview,
} from "@xingwen/domain";
import { Badge } from "@xingwen/ui";
import { TriangleAlert } from "@xingwen/ui/icons";

import { EvidenceLinks } from "../evidence-links";
import {
  ScientificTable,
  type ScientificTableColumn,
  type ScientificTableRow,
  type ScientificTableScalar,
} from "../scientific-table";
import {
  ScientificContentHeader,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

const FINDING_ALERT_STATUSES = new Set([
  "partial",
  "unverifiable",
  "conflicted",
]);

const COLUMN_LABELS: Readonly<Record<string, string>> = {
  source_id: "源标识",
  object_id: "天体标识",
  source_id_1: "源 1 标识",
  source_id_2: "源 2 标识",
  ra: "赤经",
  ra_degrees: "赤经",
  dec: "赤纬",
  dec_degrees: "赤纬",
  parallax: "视差",
  parallax_mas: "视差",
  pmra: "赤经方向自行",
  pm_ra_mas_per_year: "赤经方向自行",
  pmdec: "赤纬方向自行",
  pm_dec_mas_per_year: "赤纬方向自行",
  radial_velocity: "径向速度",
  distance_gspphot: "距离",
  occurred_at: "发生时间",
  observed_at: "观测时间",
  event: "事件",
  apparent_magnitude: "视星等",
};

function humanColumnLabel(key: string): string {
  return (
    COLUMN_LABELS[key] ??
    key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

function inferredUnit(key: string): string | null {
  if (key === "ra" || key.endsWith("ra_degrees")) return "deg";
  if (key === "dec" || key.endsWith("dec_degrees")) return "deg";
  if (key.includes("parallax") && (key === "parallax" || key.endsWith("_mas")))
    return "mas";
  if (key === "pmra" || key === "pmdec" || key.includes("mas_per_year"))
    return "mas/yr";
  if (key.includes("radial_velocity")) return "km/s";
  if (key.endsWith("_mag") || key.includes("mean_mag")) return "mag";
  if (key.endsWith("_hours")) return "h";
  if (key.endsWith("_degrees")) return "deg";
  if (key.endsWith("_minutes")) return "min";
  if (key.endsWith("_meters")) return "m";
  if (key.endsWith("_au")) return "au";
  if (key.includes("distance") && key.includes("gspphot")) return "pc";
  return null;
}

function isScalar(value: unknown): value is ScientificTableScalar {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

function recordRows(
  payload: unknown,
  representation: ScientificResultBlockReview["representation"],
): readonly Record<string, unknown>[] | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  if (representation !== "record") {
    const rows = record.rows;
    if (
      Array.isArray(rows) &&
      rows.length > 0 &&
      rows.every(
        (item) =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      )
    ) {
      return rows as readonly Record<string, unknown>[];
    }
    return null;
  }
  const scalarEntries = Object.entries(record).filter(([, value]) =>
    isScalar(value),
  );
  return scalarEntries.length > 0 ? [Object.fromEntries(scalarEntries)] : null;
}

function explicitColumns(
  payload: unknown,
): ReadonlyMap<string, ScientificTableColumn> {
  if (!payload || typeof payload !== "object") return new Map();
  const metadata = (payload as Record<string, unknown>).column_metadata;
  if (!Array.isArray(metadata)) return new Map();
  return new Map(
    metadata.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const record = item as Record<string, unknown>;
      if (typeof record.field !== "string") return [];
      return [
        [
          record.field,
          {
            key: record.field,
            label:
              typeof record.label === "string"
                ? record.label
                : humanColumnLabel(record.field),
            unit: typeof record.unit === "string" ? record.unit : null,
          },
        ] as const,
      ];
    }),
  );
}

function tableModel(
  block: ScientificResultBlockReview,
): { columns: ScientificTableColumn[]; rows: ScientificTableRow[] } | null {
  const records = recordRows(block.payload, block.representation);
  if (!records) return null;
  const explicit = explicitColumns(block.payload);
  const keys = [
    ...new Set(
      records.flatMap((record) =>
        Object.entries(record)
          .filter(([, value]) => isScalar(value))
          .map(([key]) => key),
      ),
    ),
  ];
  if (keys.length === 0) return null;
  return {
    columns: keys.map(
      (key) =>
        explicit.get(key) ?? {
          key,
          label: humanColumnLabel(key),
          unit: inferredUnit(key),
        },
    ),
    rows: records.map((record, index) => ({
      id: `${block.blockId}.${index}`,
      cells: Object.fromEntries(
        keys.map((key) => [
          key,
          {
            value: isScalar(record[key]) ? record[key] : null,
            unit: explicit.get(key)?.unit ?? inferredUnit(key),
            evidenceIds: block.evidenceIds,
          },
        ]),
      ),
    })),
  };
}

function StructuredValue({ value }: { readonly value: unknown }) {
  if (isScalar(value))
    return <span>{value === null ? "无" : String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>暂无数据</span>;
    return (
      <ol className="space-y-1 pl-5">
        {value.map((item, index) => (
          <li key={index}>
            <StructuredValue value={item} />
          </li>
        ))}
      </ol>
    );
  }
  if (value && typeof value === "object") {
    return (
      <dl className="grid gap-2">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}>
            <dt className="font-medium">{humanColumnLabel(key)}</dt>
            <dd className="text-[var(--oh-muted)]">
              <StructuredValue value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span>暂无数据</span>;
}

function sourceDetails(payload: unknown): readonly [string, string][] {
  if (!payload || typeof payload !== "object") return [];
  const record = payload as Record<string, unknown>;
  const fields: readonly [string, string][] = [
    ["service", "数据服务"],
    ["data_release", "数据版本"],
    ["catalog", "星表"],
    ["qualified_table", "数据表"],
    ["coordinate_frame", "坐标系"],
    ["frame", "参考系"],
    ["time_scale", "时间尺度"],
    ["ephemeris", "星历"],
    ["provider_uri", "服务地址"],
  ];
  return fields.flatMap(([key, label]) =>
    isScalar(record[key]) && record[key] !== null
      ? [[label, String(record[key])] as [string, string]]
      : [],
  );
}

export function ResultBlock({
  block,
  onSelectEvidence,
}: {
  readonly block: ScientificResultBlockReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const table = tableModel(block);
  const details = sourceDetails(block.payload);
  return (
    <section className="scientific-result">
      <header>
        <h4>{block.label}</h4>
      </header>
      {details.length > 0 ? (
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--oh-muted)]">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt className="inline font-medium">{label}：</dt>
              <dd className="inline">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {table ? (
        <ScientificTable
          caption={`${block.label}结构化结果`}
          columns={table.columns}
          rows={table.rows}
          maxRows={50}
          maxColumns={16}
          onSelectEvidence={
            onSelectEvidence
              ? (evidenceIds) => {
                  const first = evidenceIds[0];
                  if (first) onSelectEvidence(first);
                }
              : undefined
          }
        />
      ) : (
        <div className="scientific-result__structured">
          <StructuredValue value={block.payload} />
        </div>
      )}
      <EvidenceLinks
        evidenceIds={block.evidenceIds}
        label={`${block.label}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </section>
  );
}

export function Metrics({
  metrics,
  baseline = [],
  onSelectEvidence,
}: {
  readonly metrics: readonly ScientificMetricReview[];
  readonly baseline?: readonly ScientificMetricReview[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (metrics.length === 0) return null;
  const baselineByLabel = new Map(
    baseline.map((metric) => [metric.label, metric]),
  );
  return (
    <section className="scientific-metrics" aria-label="评估指标">
      <h4>指标</h4>
      <dl>
        {metrics.map((metric) => (
          <div key={metric.metricId}>
            <dt>{metric.label}</dt>
            <dd>
              <strong>{metric.value}</strong>
              {metric.unit ? <span>{metric.unit}</span> : null}
              {baselineByLabel.has(metric.label) ? (
                <small>基线 {baselineByLabel.get(metric.label)?.value}</small>
              ) : null}
              <EvidenceLinks
                evidenceIds={metric.evidenceIds}
                label={`${metric.label}的证据`}
                onSelectEvidence={onSelectEvidence}
              />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function Limitations({ items }: { readonly items: readonly string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="scientific-limitations">
      <h4>局限性</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function AnalysisReportContent({
  content,
  title,
  sourceMode,
  surface,
  onSelectEvidence,
}: {
  readonly content: AnalysisReportReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--analysis-report"
      data-surface={surface}
    >
      <ScientificContentHeader
        title={content.title || title}
        subtitle={`分析报告 · ${sourceModeLabel(sourceMode)}`}
      />
      <p className="artifact-view__lead">{content.summary}</p>
      <Metrics metrics={content.metrics} onSelectEvidence={onSelectEvidence} />
      {content.findings.length > 0 ? (
        <section className="scientific-findings">
          <h4>研究发现</h4>
          {content.findings.map((finding) => (
            <article key={finding.findingId} data-status={finding.status}>
              <header>
                <strong>{finding.title}</strong>
                {FINDING_ALERT_STATUSES.has(finding.status) ? (
                  <Badge variant="outline">{finding.status}</Badge>
                ) : null}
              </header>
              <p>{finding.statement}</p>
              <EvidenceLinks
                evidenceIds={finding.evidenceIds}
                label={`${finding.title}的证据`}
                onSelectEvidence={onSelectEvidence}
              />
            </article>
          ))}
        </section>
      ) : null}
      {content.resultBlocks.map((block) => (
        <ResultBlock
          key={block.blockId}
          block={block}
          onSelectEvidence={onSelectEvidence}
        />
      ))}
      <Limitations items={content.limitations} />
      {content.humanRequired.length > 0 ? (
        <section className="scientific-warning">
          <TriangleAlert aria-hidden="true" />
          <div>
            <h4>需要人工确认</h4>
            <ul>
              {content.humanRequired.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </article>
  );
}
