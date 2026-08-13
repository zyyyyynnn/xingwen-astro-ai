import type {
  AnalysisReportReviewContent,
  ContentHash,
  ModelEvaluationReviewContent,
  ScientificArtifactReview,
  ScientificMetricReview,
  ScientificResultBlockReview,
  VisualizationReviewContent,
} from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
import { Download, TriangleAlert } from "@xingwen/ui/icons";

import { ScientificChart } from "./scientific-chart";
import { WwtViewport } from "./wwt-viewport";

function displayValue(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value, null, 2);
}

function recordRows(
  payload: unknown,
): readonly Record<string, unknown>[] | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  const candidate = Object.values(record).find(
    (value) =>
      Array.isArray(value) &&
      value.length > 0 &&
      value.every(
        (item) =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      ),
  );
  return Array.isArray(candidate)
    ? (candidate as readonly Record<string, unknown>[])
    : null;
}

function ResultBlock({
  block,
}: {
  readonly block: ScientificResultBlockReview;
}) {
  const rows = recordRows(block.payload);
  const visibleRows = rows?.slice(0, 50) ?? [];
  const columns = [
    ...new Set(visibleRows.flatMap((row) => Object.keys(row))),
  ].slice(0, 12);
  return (
    <section className="scientific-result">
      <header>
        <h4>{block.label}</h4>
        <span>{block.representation}</span>
      </header>
      {rows ? (
        <div className="scientific-result__table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{displayValue(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > visibleRows.length ? (
            <p>
              当前显示前 {visibleRows.length} / {rows.length} 行。
            </p>
          ) : null}
        </div>
      ) : (
        <pre>{displayValue(block.payload)}</pre>
      )}
    </section>
  );
}

function Metrics({
  metrics,
  baseline = [],
}: {
  readonly metrics: readonly ScientificMetricReview[];
  readonly baseline?: readonly ScientificMetricReview[];
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
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function AnalysisView({
  content,
}: {
  readonly content: AnalysisReportReviewContent;
}) {
  return (
    <>
      <p className="artifact-view__lead">{content.summary}</p>
      <Metrics metrics={content.metrics} />
      {content.findings.length > 0 ? (
        <section className="scientific-findings">
          <h4>研究发现</h4>
          {content.findings.map((finding) => (
            <article key={finding.findingId} data-status={finding.status}>
              <header>
                <strong>{finding.title}</strong>
                <Badge variant="outline">{finding.status}</Badge>
              </header>
              <p>{finding.statement}</p>
            </article>
          ))}
        </section>
      ) : null}
      {content.resultBlocks.map((block) => (
        <ResultBlock key={block.blockId} block={block} />
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
    </>
  );
}

function ModelView({
  content,
}: {
  readonly content: ModelEvaluationReviewContent;
}) {
  return (
    <>
      <dl className="model-evaluation__identity">
        <div>
          <dt>任务</dt>
          <dd>{content.taskKind}</dd>
        </div>
        <div>
          <dt>算法</dt>
          <dd>{content.algorithm}</dd>
        </div>
        <div>
          <dt>算法版本</dt>
          <dd>{content.algorithmVersion}</dd>
        </div>
        <div>
          <dt>目标字段</dt>
          <dd>{content.targetField}</dd>
        </div>
      </dl>
      <section className="model-evaluation__split">
        <h4>数据划分</h4>
        <div aria-label="训练、验证和测试数据比例">
          <span style={{ flexBasis: `${content.split.trainFraction * 100}%` }}>
            训练 {(content.split.trainFraction * 100).toFixed(0)}%
          </span>
          {content.split.validationFraction > 0 ? (
            <span
              style={{
                flexBasis: `${content.split.validationFraction * 100}%`,
              }}
            >
              验证 {(content.split.validationFraction * 100).toFixed(0)}%
            </span>
          ) : null}
          <span style={{ flexBasis: `${content.split.testFraction * 100}%` }}>
            测试 {(content.split.testFraction * 100).toFixed(0)}%
          </span>
        </div>
        <p>
          {content.split.strategy}
          {content.split.randomSeed === null
            ? " · 时间有序，无随机种子"
            : ` · 随机种子 ${content.split.randomSeed}`}
        </p>
      </section>
      <Metrics metrics={content.metrics} baseline={content.baselineMetrics} />
      <section className="model-evaluation__features">
        <h4>特征字段</h4>
        <p>{content.featureFields.join("、")}</p>
      </section>
      <Limitations items={content.limitations} />
    </>
  );
}

function Limitations({ items }: { readonly items: readonly string[] }) {
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

function downloadBlob(content: ArrayBuffer, fileName: string) {
  const blob = new Blob([content], { type: "application/fits" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function VisualizationView({
  content,
  loadContent,
}: {
  readonly content: VisualizationReviewContent;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  if (content.spec.mode === "chart") {
    return <ScientificChart spec={content.spec} />;
  }
  if (content.spec.mode === "fits_image") {
    const fitsSpec = content.spec;
    return (
      <>
        <WwtViewport spec={fitsSpec} loadContent={loadContent} />
        <div className="artifact-view__actions">
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() =>
              void loadContent(fitsSpec.contentHash).then((binary) =>
                downloadBlob(binary, `${content.visualizationId}.fits`),
              )
            }
          >
            <Download data-icon="inline-start" aria-hidden="true" />
            下载原始 FITS
          </Button>
          <span>
            {fitsSpec.stretch} 拉伸 · {fitsSpec.colorMap} 色图
          </span>
        </div>
      </>
    );
  }
  if (content.spec.mode === "wwt_scene") {
    return (
      <>
        <WwtViewport spec={content.spec} loadContent={loadContent} />
        <dl className="wwt-scene__metadata">
          <div>
            <dt>中心</dt>
            <dd>
              RA {content.spec.center.raHours.toFixed(4)}h · Dec{" "}
              {content.spec.center.decDegrees.toFixed(4)}°
            </dd>
          </div>
          <div>
            <dt>视场</dt>
            <dd>{content.spec.fieldOfViewDegrees}°</dd>
          </div>
          <div>
            <dt>坐标网格</dt>
            <dd>{content.spec.coordinateGrid}</dd>
          </div>
          <div>
            <dt>图层 / 标注</dt>
            <dd>
              {content.spec.fitsLayers.length} /{" "}
              {content.spec.annotations.length}
            </dd>
          </div>
        </dl>
      </>
    );
  }
  return (
    <section className="scientific-diagnostic">
      <h4>模型诊断</h4>
      <p>{content.spec.diagnostic}</p>
      <p>关联模型评估 {content.spec.modelEvaluationArtifactVersionId}</p>
    </section>
  );
}

export function ScientificArtifactView({
  artifact,
  loadContent,
}: {
  readonly artifact: ScientificArtifactReview;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  const { content } = artifact;
  return (
    <article className="scientific-artifact" aria-label={content.title}>
      <header className="artifact-view__header">
        <p className="artifact-view__eyebrow">
          {content.kind} · v{artifact.versionNumber}
        </p>
        <h3>{content.title}</h3>
        {content.kind === "visualization" ? <p>{content.description}</p> : null}
        <div className="artifact-view__badges">
          <Badge variant="outline">{artifact.sourceMode}</Badge>
          <Badge variant="outline">
            来源快照 {artifact.sourceSnapshots.length}
          </Badge>
          <Badge variant="outline">证据 {artifact.evidence.length}</Badge>
        </div>
      </header>
      {content.kind === "analysis_report" ? (
        <AnalysisView content={content} />
      ) : content.kind === "model_evaluation" ? (
        <ModelView content={content} />
      ) : (
        <VisualizationView content={content} loadContent={loadContent} />
      )}
      <details className="artifact-view__provenance">
        <summary>复现与来源信息</summary>
        <dl>
          <div>
            <dt>制品内容哈希</dt>
            <dd>{artifact.contentHash}</dd>
          </div>
          <div>
            <dt>输入哈希</dt>
            <dd>{artifact.inputHash}</dd>
          </div>
          <div>
            <dt>生产者</dt>
            <dd>
              {artifact.producerExecution.producerName} ·{" "}
              {artifact.producerExecution.producerVersion}
            </dd>
          </div>
        </dl>
        {artifact.sourceSnapshots.map((snapshot) => (
          <p key={snapshot.id}>
            {snapshot.sourceId} · {snapshot.contentHash} ·{" "}
            {snapshot.licenseNote}
          </p>
        ))}
      </details>
    </article>
  );
}
