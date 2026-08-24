import type { JsonValue, PublicArtifactVersion } from "@xingwen/domain";
import type { ReactNode } from "react";

import { artifactKindLabel } from "../presentation/artifact-presentation-labels";
import {
  polarityLabel,
  reviewStatusLabel,
  taxonomyLabel,
} from "./scientific-content/shared";

type JsonRecord = Readonly<Record<string, JsonValue>>;

function record(value: JsonValue | undefined): JsonRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : null;
}

function records(value: JsonValue | undefined): readonly JsonRecord[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const mapped = record(item);
        return mapped ? [mapped] : [];
      })
    : [];
}

function text(value: JsonValue | undefined): string | null {
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function texts(value: JsonValue | undefined): readonly string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const mapped = text(item);
        return mapped ? [mapped] : [];
      })
    : [];
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function firstText(value: JsonRecord, keys: readonly string[]): string | null {
  for (const key of keys) {
    const candidate = text(value[key]);
    if (candidate) return candidate;
  }
  return null;
}

function count(
  value: JsonRecord,
  numericKeys: readonly string[],
  collectionKeys: readonly string[],
): number | null {
  for (const key of numericKeys) {
    const candidate = numberValue(value[key]);
    if (candidate !== null) return candidate;
  }
  for (const key of collectionKeys) {
    if (Array.isArray(value[key])) return value[key].length;
  }
  return null;
}

function FactStrip({
  facts,
}: {
  readonly facts: readonly { readonly label: string; readonly value: string }[];
}) {
  if (facts.length === 0) return null;
  return (
    <dl className="public-artifact__facts">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EmptyPublicContent() {
  return (
    <p className="public-artifact__empty">
      该结果的公开副本未包含可安全展示的正文。
    </p>
  );
}

function DataContent({ version }: { readonly version: PublicArtifactVersion }) {
  const content = version.content;
  const rows = records(content.rows);
  const columns = records(content.columns);
  const fields = records(content.field_definitions);
  const members = records(content.members);
  const rowCount = count(content, ["row_count"], ["rows"]);
  const fieldCount = count(
    content,
    ["field_count"],
    ["columns", "field_definitions"],
  );
  const facts = [
    ...(rowCount === null ? [] : [{ label: "记录", value: `${rowCount} 条` }]),
    ...(fieldCount === null
      ? []
      : [{ label: "字段", value: `${fieldCount} 个` }]),
    ...(members.length === 0
      ? []
      : [{ label: "来源", value: `${members.length} 个` }]),
  ];
  const visibleFields = (fields.length > 0 ? fields : columns).slice(0, 12);

  return (
    <>
      <FactStrip facts={facts} />
      {visibleFields.length > 0 ? (
        <section className="public-artifact__section">
          <h3>字段说明</h3>
          <dl className="public-artifact__definition-list">
            {visibleFields.map((field, index) => {
              const nested = record(field.field);
              const source = nested ?? field;
              const label =
                firstText(source, ["meaning_zh", "label_en", "name"]) ??
                `字段 ${index + 1}`;
              const description =
                firstText(source, [
                  "description",
                  "canonical_unit",
                  "data_type",
                ]) ?? "公开副本未提供更多说明";
              return (
                <div key={`${label}-${index}`}>
                  <dt>{label}</dt>
                  <dd>{description}</dd>
                </div>
              );
            })}
          </dl>
        </section>
      ) : null}
      {rows.length > 0 ? (
        <section className="public-artifact__section">
          <h3>数据预览</h3>
          <ol className="public-artifact__record-list">
            {rows.slice(0, 12).map((row, index) => {
              const authority = record(row.row_authority);
              const identity =
                firstText(row, ["label", "identity"]) ??
                (authority
                  ? firstText(authority, ["canonical_identity", "entity_level"])
                  : null) ??
                `记录 ${index + 1}`;
              return <li key={`${identity}-${index}`}>{identity}</li>;
            })}
          </ol>
        </section>
      ) : null}
      {facts.length === 0 && visibleFields.length === 0 && rows.length === 0 ? (
        <EmptyPublicContent />
      ) : null}
    </>
  );
}

function LiteratureContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  const content = version.content;
  const items =
    version.kind === "literature_claims"
      ? records(content.claims)
      : records(content.relations);
  const itemLabel = version.kind === "literature_claims" ? "论点" : "关系";

  if (items.length === 0) return <EmptyPublicContent />;
  return (
    <section className="public-artifact__section">
      <h3>{itemLabel}摘要</h3>
      <ol className="public-artifact__cards">
        {items.map((item, index) => {
          const direction = record(item.direction);
          const trace = record(item.reasoning_trace) ?? record(item.trace);
          const relationType = text(item.relation_type);
          const heading =
            firstText(item, ["text", "normalized_text"]) ??
            (relationType ? taxonomyLabel(relationType) : null) ??
            `${itemLabel} ${index + 1}`;
          const status = text(item.status);
          const claimType = text(item.claim_type);
          const polarity = text(item.polarity);
          const stateLabel = status
            ? reviewStatusLabel(status)
            : claimType
              ? taxonomyLabel(claimType)
              : polarity
                ? polarityLabel(polarity)
                : "已纳入公开副本";
          const conclusion = trace
            ? firstText(trace, ["conclusion", "statement"])
            : null;
          const details = [
            ...texts(item.objects),
            ...texts(item.scope),
            ...texts(item.conditions),
            ...texts(item.limitations),
            ...(direction
              ? [text(direction.basis)].filter(
                  (candidate): candidate is string => candidate !== null,
                )
              : []),
          ].slice(0, 6);
          return (
            <li key={`${heading}-${index}`}>
              <h4>{heading}</h4>
              {conclusion ? <p>{conclusion}</p> : null}
              {details.length > 0 ? <p>{details.join("；")}</p> : null}
              <span>{stateLabel}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function GraphContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  const content = version.content;
  const graph = record(content.graph) ?? content;
  const nodes = records(content.nodes).map((item) => record(item.node) ?? item);
  const edges = records(content.edges).map((item) => record(item.edge) ?? item);
  const nodeCount = count(graph, ["node_count"], []) ?? nodes.length;
  const edgeCount = count(graph, ["edge_count"], []) ?? edges.length;

  return (
    <>
      <FactStrip
        facts={[
          { label: "研究对象", value: `${nodeCount} 个` },
          { label: "证据关系", value: `${edgeCount} 条` },
        ]}
      />
      {nodes.length > 0 ? (
        <section className="public-artifact__section">
          <h3>关系图对象</h3>
          <ul className="public-artifact__tag-list">
            {nodes.slice(0, 24).map((node, index) => (
              <li key={`${firstText(node, ["label"]) ?? "node"}-${index}`}>
                {firstText(node, ["label"]) ?? `对象 ${index + 1}`}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="public-artifact__empty">
          关系图统计已冻结；公开副本未包含可展示的对象标签。
        </p>
      )}
    </>
  );
}

const PAPER_SECTIONS = [
  ["研究背景", "background"],
  ["研究方法", "methodology"],
  ["数据集", "dataset"],
  ["实验与结果", "experiments"],
  ["讨论", "discussion"],
  ["局限性", "limitations"],
  ["研究问题", "research_questions"],
] as const;

function PaperSummaryContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  const sections = PAPER_SECTIONS.flatMap(([label, key]) => {
    const statements = records(version.content[key]).flatMap((item) => {
      const statement = firstText(item, ["text", "statement", "content"]);
      return statement ? [statement] : [];
    });
    return statements.length > 0 ? [{ label, statements }] : [];
  });
  if (sections.length === 0) return <EmptyPublicContent />;
  return (
    <div className="public-artifact__paper">
      {sections.map((section) => (
        <section key={section.label} className="public-artifact__section">
          <h3>{section.label}</h3>
          {section.statements.map((statement, index) => (
            <p key={`${section.label}-${index}`}>{statement}</p>
          ))}
        </section>
      ))}
    </div>
  );
}

function GeneralContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  const content = version.content;
  const title = firstText(content, ["title", "name"]);
  const description = firstText(content, [
    "description",
    "summary",
    "conclusion",
  ]);
  const metrics = records(content.metrics).slice(0, 12);
  const candidates = records(content.candidates).slice(0, 12);
  const facts = [
    ...(["sample_count", "selected_count", "candidate_count"] as const).flatMap(
      (key) => {
        const value = numberValue(content[key]);
        return value === null ? [] : [{ label: "数量", value: String(value) }];
      },
    ),
  ].slice(0, 1);

  return (
    <>
      <FactStrip facts={facts} />
      {title && title !== version.title ? <h3>{title}</h3> : null}
      {description ? (
        <p className="public-artifact__lead">{description}</p>
      ) : null}
      {metrics.length > 0 ? (
        <dl className="public-artifact__definition-list">
          {metrics.map((metric, index) => (
            <div
              key={`${firstText(metric, ["name", "label"]) ?? "metric"}-${index}`}
            >
              <dt>
                {firstText(metric, ["name", "label"]) ?? `指标 ${index + 1}`}
              </dt>
              <dd>{firstText(metric, ["value", "display_value"]) ?? "—"}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {candidates.length > 0 ? (
        <ol className="public-artifact__record-list">
          {candidates.map((candidate, index) => (
            <li key={`${firstText(candidate, ["title"]) ?? "paper"}-${index}`}>
              {firstText(candidate, ["title"]) ?? `论文 ${index + 1}`}
            </li>
          ))}
        </ol>
      ) : null}
      {!title &&
      !description &&
      metrics.length === 0 &&
      candidates.length === 0 ? (
        <EmptyPublicContent />
      ) : null}
    </>
  );
}

function PublicArtifactFrame({
  version,
  children,
}: {
  readonly version: PublicArtifactVersion;
  readonly children: ReactNode;
}) {
  return (
    <article className="public-artifact" data-kind={version.kind}>
      <header className="public-artifact__header">
        <p>{artifactKindLabel(version.kind)}</p>
        <h2>{version.title}</h2>
      </header>
      {children}
    </article>
  );
}

export function PublicDataArtifactContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  return (
    <PublicArtifactFrame version={version}>
      <DataContent version={version} />
    </PublicArtifactFrame>
  );
}

export function PublicLiteratureArtifactContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  return (
    <PublicArtifactFrame version={version}>
      <LiteratureContent version={version} />
    </PublicArtifactFrame>
  );
}

export function PublicGraphArtifactContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  return (
    <PublicArtifactFrame version={version}>
      <GraphContent version={version} />
    </PublicArtifactFrame>
  );
}

export function PublicPaperSummaryArtifactContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  return (
    <PublicArtifactFrame version={version}>
      <PaperSummaryContent version={version} />
    </PublicArtifactFrame>
  );
}

export function PublicGeneralArtifactContent({
  version,
}: {
  readonly version: PublicArtifactVersion;
}) {
  return (
    <PublicArtifactFrame version={version}>
      <GeneralContent version={version} />
    </PublicArtifactFrame>
  );
}
