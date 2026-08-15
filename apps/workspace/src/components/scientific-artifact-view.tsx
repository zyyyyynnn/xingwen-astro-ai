import type {
  AnalysisReportReviewContent,
  ContentHash,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
  ScientificArtifactReview,
  ScientificMetricReview,
  ScientificResultBlockReview,
  DomainEntityId,
  VisualizationReviewContent,
} from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
import { Download, TriangleAlert } from "@xingwen/ui/icons";

import { ScientificChart } from "./scientific-chart";
import { WwtViewport } from "./wwt-viewport";
import { downloadBytes } from "../presentation/browser-download";
import { EvidenceLinks } from "./evidence-links";

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
  onSelectEvidence,
}: {
  readonly block: ScientificResultBlockReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
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
      <EvidenceLinks
        evidenceIds={block.evidenceIds}
        label={`${block.label}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </section>
  );
}

function Metrics({
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

function AnalysisView({
  content,
  onSelectEvidence,
}: {
  readonly content: AnalysisReportReviewContent;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  return (
    <>
      <p className="artifact-view__lead">{content.summary}</p>
      <Metrics metrics={content.metrics} onSelectEvidence={onSelectEvidence} />
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
    </>
  );
}

function ModelEvaluationView({
  content,
  onSelectEvidence,
}: {
  readonly content: ModelEvaluationReviewContent;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
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
      <Metrics
        metrics={content.metrics}
        baseline={content.baselineMetrics}
        onSelectEvidence={onSelectEvidence}
      />
      <section className="model-evaluation__features">
        <h4>特征字段</h4>
        <p>{content.featureFields.join("、")}</p>
      </section>
      <Limitations items={content.limitations} />
    </>
  );
}

function ModelArtifactView({
  content,
  loadContent,
}: {
  readonly content: ModelArtifactReviewContent;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  return (
    <>
      <dl className="model-evaluation__identity">
        <div>
          <dt>状态</dt>
          <dd>{content.status}</dd>
        </div>
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
      </dl>
      <section className="model-evaluation__features">
        <h4>推理契约</h4>
        <dl className="wwt-scene__metadata">
          <div>
            <dt>输入</dt>
            <dd>{content.inputName}</dd>
          </div>
          <div>
            <dt>形状</dt>
            <dd>
              {content.inputShape.map((value) => value ?? "batch").join(" × ")}
            </dd>
          </div>
          <div>
            <dt>输出</dt>
            <dd>{content.outputNames.join("、")}</dd>
          </div>
          <div>
            <dt>目标字段</dt>
            <dd>{content.targetField}</dd>
          </div>
        </dl>
        <p>{content.featureFields.join("、")}</p>
      </section>
      <section className="model-evaluation__features">
        <h4>运行依赖</h4>
        <p>{content.dependencyRevisions.join(" · ")}</p>
      </section>
      <div className="artifact-view__actions">
        <Button
          type="button"
          variant="secondary"
          size="small"
          disabled={content.status !== "active"}
          onClick={() =>
            void loadContent(content.modelBinary.contentHash).then((binary) =>
              downloadBytes({
                bytes: binary,
                fileName: `${content.modelId}.onnx`,
                mediaType: content.modelBinary.mediaType,
              }),
            )
          }
        >
          <Download data-icon="inline-start" aria-hidden="true" />
          下载 ONNX 模型
        </Button>
        <span>{content.modelBinary.contentHash}</span>
      </div>
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

function VisualizationView({
  content,
  versionNumber,
  loadContent,
  onSelectEvidence,
}: {
  readonly content: VisualizationReviewContent;
  readonly versionNumber: number;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (content.spec.mode === "chart") {
    return (
      <>
        <ScientificChart spec={content.spec} />
        <EvidenceLinks
          evidenceIds={content.evidenceIds}
          label="图表证据"
          onSelectEvidence={onSelectEvidence}
        />
      </>
    );
  }
  if (content.spec.mode === "fits_image") {
    const fitsSpec = content.spec;
    return (
      <>
        <WwtViewport
          spec={fitsSpec}
          versionNumber={versionNumber}
          loadContent={loadContent}
        />
        <EvidenceLinks
          evidenceIds={content.evidenceIds}
          label="FITS 图像证据"
          onSelectEvidence={onSelectEvidence}
        />
        <div className="artifact-view__actions">
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() =>
              void loadContent(fitsSpec.contentHash).then((binary) =>
                downloadBytes({
                  bytes: binary,
                  fileName: `${content.visualizationId}.fits`,
                  mediaType: "application/fits",
                }),
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
        <WwtViewport
          spec={content.spec}
          versionNumber={versionNumber}
          loadContent={loadContent}
        />
        <EvidenceLinks
          evidenceIds={content.evidenceIds}
          label="WWT 场景证据"
          onSelectEvidence={onSelectEvidence}
        />
        <dl className="wwt-scene__metadata">
          <div>
            <dt>视图</dt>
            <dd>
              {content.spec.view.kind === "coordinates"
                ? `RA ${content.spec.view.center.raHours.toFixed(4)}h · Dec ${content.spec.view.center.decDegrees.toFixed(4)}°`
                : `跟踪 ${content.spec.view.target}`}
            </dd>
          </div>
          <div>
            <dt>视场</dt>
            <dd>{content.spec.view.fieldOfViewDegrees}°</dd>
          </div>
          <div>
            <dt>坐标网格</dt>
            <dd>
              {content.spec.coordinateGrids.length > 0
                ? content.spec.coordinateGrids
                    .map((grid) => grid.system)
                    .join("、")
                : "未启用"}
            </dd>
          </div>
          <div>
            <dt>FITS / 表格 / 标注</dt>
            <dd>
              {content.spec.fitsLayers.length} /{" "}
              {content.spec.tableLayers.length} /{" "}
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
  onSelectEvidence,
}: {
  readonly artifact: ScientificArtifactReview;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const { content } = artifact;
  return (
    <article className="scientific-artifact" aria-label={content.title}>
      <header className="artifact-view__header">
        <h3>{content.title}</h3>
        {content.kind === "visualization" ? <p>{content.description}</p> : null}
        <div className="artifact-view__badges">
          <Badge variant="outline">
            {content.kind} · v{artifact.versionNumber}
          </Badge>
          <Badge variant="outline">{artifact.sourceMode}</Badge>
          <Badge variant="outline">
            来源快照 {artifact.sourceSnapshots.length}
          </Badge>
          <Badge variant="outline">证据 {artifact.evidence.length}</Badge>
        </div>
      </header>
      {content.kind === "analysis_report" ? (
        <AnalysisView content={content} onSelectEvidence={onSelectEvidence} />
      ) : content.kind === "model_evaluation" ? (
        <ModelEvaluationView
          content={content}
          onSelectEvidence={onSelectEvidence}
        />
      ) : content.kind === "model_artifact" ? (
        <ModelArtifactView content={content} loadContent={loadContent} />
      ) : content.kind === "visualization" ? (
        <VisualizationView
          content={content}
          versionNumber={artifact.versionNumber}
          loadContent={loadContent}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <p className="artifact-view__empty">
          该科学产物由统一科学结果渲染器展示。
        </p>
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
