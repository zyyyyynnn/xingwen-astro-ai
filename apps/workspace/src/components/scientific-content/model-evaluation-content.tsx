import { useState } from "react";
import type {
  ContentHash,
  DomainEntityId,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
} from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Spinner,
} from "@xingwen/ui";
import { ChevronRight, Download, Info } from "@xingwen/ui/icons";

import { downloadBytes } from "../../presentation/browser-download";
import { EvidenceLinks } from "../evidence-links";
import {
  ScientificContentHeader,
  formatNumber,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

const TASK_KIND_LABELS: Record<string, string> = {
  classification: "分类任务 (Classification)",
  regression: "回归任务 (Regression)",
  forecast: "时序预测 (Forecast)",
  image_classification: "图像分类",
  time_series_classification: "时间序列分类 (Transit Identification)",
};

const SPLIT_STRATEGY_LABELS: Record<
  ModelEvaluationReviewContent["split"]["strategy"],
  string
> = {
  random: "随机划分 (Random Split)",
  stratified: "分层划分 (Stratified Split)",
  group: "分组划分 (Group Split)",
  entity: "实体隔离划分 (Target Entity Split)",
  time: "时间顺序划分 (Temporal Split)",
};

function taskKindLabel(value: string): string {
  return TASK_KIND_LABELS[value] ?? value;
}

const OUTPUT_KIND_LABELS = {
  tensor: "张量",
  sparse_tensor: "稀疏张量",
  sequence: "序列",
  map: "映射",
  optional: "可选值",
};

const ALGORITHM_LABELS: Readonly<Record<string, string>> = {
  random_forest: "随机森林",
  logistic_regression: "逻辑回归",
  linear_regression: "线性回归",
  random_forest_autoregression: "随机森林自回归",
};

function algorithmLabel(value: string): string {
  return ALGORITHM_LABELS[value] ?? value;
}

export function ModelEvaluationContent({
  content,
  title,
  sourceMode,
  surface,
  onSelectEvidence,
  enhancementOnly = false,
}: {
  readonly content: ModelEvaluationReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly enhancementOnly?: boolean;
}) {
  const trainPct = (content.split.trainFraction * 100).toFixed(0);
  const valPct = (content.split.validationFraction * 100).toFixed(0);
  const testPct = (content.split.testFraction * 100).toFixed(0);
  const fixtureMode = sourceMode === "fixture";
  const holdoutMetrics = content.metrics.filter(
    (metric) => metric.category === "holdout",
  );
  const supportingMetrics = content.metrics.filter(
    (metric) => metric.category !== "holdout",
  );

  return (
    <article
      className="scientific-artifact scientific-artifact--model-evaluation space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`${algorithmLabel(content.algorithm)} · ${content.algorithmVersion}`}
          />

          <div className="model-report__facts" aria-label="模型属性">
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">任务类型</div>
              <div className="mt-1 text-sm font-semibold">
                {taskKindLabel(content.taskKind)}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">核心算法</div>
              <div className="mt-1 text-sm font-semibold">
                {algorithmLabel(content.algorithm)}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">目标字段</div>
              <div className="mt-1 text-sm font-semibold font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">训练输入</div>
              <div className="mt-1 text-sm font-semibold">
                {content.trainingInput.kind === "dataset_artifact_version"
                  ? "研究数据集"
                  : "来源快照"}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">划分策略</div>
              <div className="mt-1 text-sm font-semibold">
                {SPLIT_STRATEGY_LABELS[content.split.strategy]}
              </div>
            </div>
            {content.split.field ? (
              <div className="model-report__fact">
                <div className="text-xs model-report__secondary">划分字段</div>
                <div className="mt-1 text-sm font-semibold font-mono">
                  {content.split.field}
                </div>
              </div>
            ) : null}
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">交叉验证</div>
              <div className="mt-1 text-sm font-semibold">
                {content.split.crossValidationFolds
                  ? `${content.split.crossValidationFolds} 折 CV`
                  : "未执行交叉验证"}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">数据源模式</div>
              <div className="mt-1 text-sm font-semibold">
                <Badge variant="secondary">{sourceModeLabel(sourceMode)}</Badge>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <section className="model-report__section model-report__split">
        <div className="mb-2 flex items-center justify-between text-xs model-report__secondary">
          <span className="font-semibold">
            数据集划分比例 (Train / Val / Test Split)
          </span>
          <span>
            {fixtureMode
              ? "界面状态覆盖，非训练运行"
              : content.split.strategy === "time"
                ? "按观测时间顺序划分"
                : "训练与测试样本分离"}
          </span>
        </div>
        <div className="model-report__split-bar">
          <div
            style={{ width: `${trainPct}%` }}
            className="flex items-center justify-center bg-[var(--color-info)]"
          >
            训练 {trainPct}%
          </div>
          {Number(valPct) > 0 && (
            <div
              style={{ width: `${valPct}%` }}
              className="flex items-center justify-center bg-[var(--color-success)]"
            >
              验证 {valPct}%
            </div>
          )}
          <div
            style={{ width: `${testPct}%` }}
            className="flex items-center justify-center bg-[var(--color-warning)]"
          >
            测试 {testPct}%
          </div>
        </div>
      </section>

      {holdoutMetrics.length > 0 ? (
        <section className="model-report__section space-y-3">
          <h4 className="text-sm font-semibold">评估指标</h4>
          <div className="model-report__metrics">
            {holdoutMetrics.map((metric) => {
              const baseline = content.baselineMetrics?.find(
                (b) => b.metricKey === metric.metricKey,
              );
              const delta =
                typeof metric.value === "number" &&
                typeof baseline?.value === "number"
                  ? metric.value - baseline.value
                  : null;
              const comparison =
                delta === null || delta === 0 || metric.optimization === "none"
                  ? "neutral"
                  : (metric.optimization === "minimize" ? delta < 0 : delta > 0)
                    ? "improved"
                    : "degraded";

              return (
                <div key={metric.metricId} className="model-report__metric">
                  <div className="text-xs model-report__secondary">
                    {metric.label}
                  </div>
                  <div className="mt-1 text-2xl font-bold">
                    {typeof metric.value === "number"
                      ? formatNumber(metric.value, 3)
                      : metric.value}
                    {metric.unit ? (
                      <span className="ml-1 text-xs font-normal model-report__secondary">
                        {metric.unit}
                      </span>
                    ) : null}
                  </div>
                  {delta !== null ? (
                    <div
                      className="model-report__comparison"
                      data-comparison={comparison}
                    >
                      {delta >= 0 ? "+" : ""}
                      {formatNumber(delta, 3)} 对比基线
                      {comparison !== "neutral"
                        ? ` · ${comparison === "improved" ? "改善" : "下降"}`
                        : ""}
                    </div>
                  ) : (
                    <div className="mt-1 text-xs model-report__secondary">
                      测试集独立评估
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <EvidenceLinks
            evidenceIds={[
              ...new Set(
                holdoutMetrics.flatMap((metric) => metric.evidenceIds),
              ),
            ]}
            onSelectEvidence={onSelectEvidence}
          />
        </section>
      ) : null}

      {supportingMetrics.length > 0 ? (
        <Collapsible className="model-report__section">
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="model-report__diagnostic-trigger"
            >
              <ChevronRight aria-hidden="true" />
              交叉验证与特征重要性 · {supportingMetrics.length} 项
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="model-report__diagnostic-content">
            {(["cross_validation", "feature_importance"] as const).map(
              (category) => {
                const metrics = supportingMetrics.filter(
                  (metric) => metric.category === category,
                );
                if (!metrics.length) return null;
                const label =
                  category === "cross_validation"
                    ? "全样本交叉验证"
                    : "特征重要性（模型贡献，不代表因果关系）";
                return (
                  <div
                    key={category}
                    className="scientific-table model-report__diagnostic-table model-report__statistics-table"
                    role="region"
                    aria-label={label}
                    tabIndex={0}
                  >
                    <table>
                      <caption>{label}</caption>
                      <thead>
                        <tr>
                          <th scope="col">
                            {category === "feature_importance"
                              ? "特征"
                              : "统计量"}
                          </th>
                          <th scope="col">数值</th>
                          {onSelectEvidence ? (
                            <th
                              scope="col"
                              className="model-report__evidence-cell"
                            >
                              依据
                            </th>
                          ) : null}
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.map((metric) => (
                          <tr key={metric.metricId}>
                            <th scope="row">{metric.label}</th>
                            <td>
                              {typeof metric.value === "number"
                                ? formatNumber(metric.value, 6)
                                : metric.value}
                              {metric.unit ? ` ${metric.unit}` : ""}
                            </td>
                            {onSelectEvidence ? (
                              <td className="model-report__evidence-cell">
                                <EvidenceLinks
                                  evidenceIds={metric.evidenceIds}
                                  onSelectEvidence={onSelectEvidence}
                                />
                              </td>
                            ) : null}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              },
            )}
          </CollapsibleContent>
        </Collapsible>
      ) : null}

      {content.diagnostics ? (
        <ModelDiagnostics
          key={content.evaluationId}
          diagnostics={content.diagnostics}
          targetField={content.targetField}
        />
      ) : null}

      <div className="model-report__supporting-grid">
        {content.featureFields.length > 0 ? (
          <section className="model-report__section">
            <h4 className="mb-2 text-sm font-semibold">
              输入特征字段 (Feature Input Fields)
            </h4>
            <ul className="model-report__feature-list">
              {content.featureFields.map((f) => (
                <li key={f}>
                  <code>{f}</code>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {content.limitations.length > 0 && !enhancementOnly ? (
          <section className="model-report__section">
            <h4 className="mb-2 text-sm font-semibold">
              模型局限性与适用边界 (Limitations)
            </h4>
            <ul className="space-y-1.5 text-xs model-report__secondary">
              {content.limitations.map((lim, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <span className="mt-0.5 inline-block size-1.5 rounded-full bg-[var(--color-warning)]" />
                  <span>{lim}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </article>
  );
}

function ModelDiagnostics({
  diagnostics,
  targetField,
}: {
  readonly diagnostics: NonNullable<
    ModelEvaluationReviewContent["diagnostics"]
  >;
  readonly targetField: string;
}) {
  const [forecastPage, setForecastPage] = useState(0);
  const pageSize = 50;
  const matrix = diagnostics.confusionMatrix;
  const predictions = diagnostics.regressionPredictions;
  const forecast = diagnostics.forecast.slice(
    forecastPage * pageSize,
    (forecastPage + 1) * pageSize,
  );
  return (
    <Collapsible className="model-report__section model-report__diagnostics">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="model-report__diagnostic-trigger">
          <ChevronRight aria-hidden="true" />
          测试集诊断 · {diagnostics.evaluatedSampleCount} 个样本
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="model-report__diagnostic-content">
        {matrix ? (
          <div
            className="scientific-table model-report__diagnostic-table"
            role="region"
            aria-label="分类混淆矩阵"
            tabIndex={0}
          >
            <table>
              <caption>混淆矩阵 · 行为实际类别，列为预测类别（样本数）</caption>
              <thead>
                <tr>
                  <th scope="col">实际 / 预测</th>
                  {matrix.labels.map((label, index) => (
                    <th key={index} scope="col">
                      {String(label)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <th scope="row">{String(matrix.labels[rowIndex])}</th>
                    {row.map((value, colIndex) => (
                      <td key={colIndex} data-diagonal={rowIndex === colIndex}>
                        {value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {predictions.length ? (
          <div
            className="scientific-table model-report__diagnostic-table"
            role="region"
            aria-label="测试集预测明细"
            tabIndex={0}
          >
            <table>
              <caption>
                {targetField} ·{" "}
                {predictions.length === diagnostics.evaluatedSampleCount
                  ? "全部测试样本"
                  : `均匀抽取 ${predictions.length} / ${diagnostics.evaluatedSampleCount} 个测试样本`}
              </caption>
              <thead>
                <tr>
                  <th scope="col">样本</th>
                  <th scope="col">实际值</th>
                  <th scope="col">预测值</th>
                </tr>
              </thead>
              <tbody>
                {predictions.map((point, index) => (
                  <tr key={point.rowId}>
                    <th scope="row">{index + 1}</th>
                    <td>{formatNumber(point.actual, 6)}</td>
                    <td>{formatNumber(point.predicted, 6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {forecast.length ? (
          <section aria-label="未来预测">
            <div
              className="scientific-table model-report__diagnostic-table"
              role="region"
              aria-label="未来预测数值"
              tabIndex={0}
            >
              <table>
                <caption>{targetField} · 递归预测，步数表示观测顺序</caption>
                <thead>
                  <tr>
                    <th scope="col">未来步数</th>
                    <th scope="col">预测值</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.map((point) => (
                    <tr key={point.step}>
                      <th scope="row">{point.step}</th>
                      <td>{formatNumber(point.predictedValue, 6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {diagnostics.forecast.length > pageSize ? (
              <nav
                aria-label="预测结果分页"
                className="model-report__diagnostic-pagination"
              >
                <Button
                  variant="secondary"
                  size="small"
                  disabled={forecastPage === 0}
                  onClick={() => setForecastPage((page) => page - 1)}
                >
                  上一页
                </Button>
                <span role="status">
                  第 {forecast[0]?.step}
                  {forecast.length > 1 ? `–${forecast.at(-1)?.step}` : ""}{" "}
                  步，共 {diagnostics.forecast.length} 步
                </span>
                <Button
                  variant="secondary"
                  size="small"
                  disabled={
                    (forecastPage + 1) * pageSize >= diagnostics.forecast.length
                  }
                  onClick={() => setForecastPage((page) => page + 1)}
                >
                  下一页
                </Button>
              </nav>
            ) : null}
          </section>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ModelArtifactContent({
  content,
  title,
  sourceMode,
  surface,
  loadContent,
  enhancementOnly = false,
}: {
  readonly content: ModelArtifactReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly enhancementOnly?: boolean;
}) {
  const [downloadState, setDownloadState] = useState<
    "idle" | "pending" | "error"
  >("idle");
  const fixtureMode = sourceMode === "fixture";
  const canDownload =
    !fixtureMode && content.status === "active" && loadContent !== undefined;
  const statusLabel = fixtureMode
    ? "不可部署"
    : content.status === "active"
      ? "可用"
      : content.status === "deprecated"
        ? "已停用"
        : "已撤销";

  const handleDownload = async () => {
    if (!canDownload || !loadContent) return;
    try {
      setDownloadState("pending");
      const binary = await loadContent(content.modelBinary.contentHash);
      downloadBytes({
        bytes: binary,
        fileName: `${content.algorithm}.onnx`,
        mediaType: content.modelBinary.mediaType,
      });
      setDownloadState("idle");
    } catch {
      setDownloadState("error");
    }
  };

  return (
    <article
      className="scientific-artifact scientific-artifact--model-artifact space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`ONNX 模型交付产物包 · ${algorithmLabel(content.algorithm)} · ${content.algorithmVersion}`}
          />

          <div
            className="model-report__facts model-report__facts--artifact"
            aria-label="产物参数"
          >
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">产物状态</div>
              <div className="model-report__fact-value model-report__fact-value--status">
                <Badge
                  variant={
                    fixtureMode || content.status === "deprecated"
                      ? "secondary"
                      : content.status === "active"
                        ? "default"
                        : "destructive"
                  }
                >
                  {statusLabel}
                </Badge>
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">模型格式</div>
              <div className="model-report__fact-value">ONNX</div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">目标字段</div>
              <div className="model-report__fact-value font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">输入张量</div>
              <div className="model-report__fact-value font-mono">
                {content.inputName}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">输出值</div>
              <div className="model-report__fact-value font-mono">
                {content.outputNames.join(", ")}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs model-report__secondary">数据源模式</div>
              <div className="model-report__fact-value">
                <Badge variant="secondary">{sourceModeLabel(sourceMode)}</Badge>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <section className="model-report__section model-report__contract">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">
            推理输入输出规格 (ONNX I/O Signature)
          </h4>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="model-report__signature">
            <div className="text-xs font-semibold">输入规格 (Inputs)</div>
            <div className="mt-2 space-y-1 text-xs">
              <div className="model-report__signature-row">
                <span className="model-report__secondary">张量名称:</span>{" "}
                <span className="font-mono font-medium">
                  {content.inputName}
                </span>
              </div>
              <div className="model-report__signature-row">
                <span className="model-report__secondary">张量形状:</span>{" "}
                <span className="font-mono font-medium">
                  [{content.inputShape.map((v) => v ?? "动态").join(", ")}]
                </span>
              </div>
              {content.inputDtype !== null ? (
                <div className="model-report__signature-row">
                  <span className="model-report__secondary">数据类型:</span>{" "}
                  <span className="font-mono font-medium">
                    {content.inputDtype}
                  </span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="model-report__signature">
            <div className="text-xs font-semibold">输出规格 (Outputs)</div>
            {content.outputNames.map((name) => {
              const metadata = content.outputMetadata[name];
              return (
                <dl key={name} className="model-report__output">
                  <div className="model-report__signature-row">
                    <dt className="model-report__secondary">输出名称</dt>
                    <dd className="font-mono font-medium">{name}</dd>
                  </div>
                  {metadata ? (
                    <>
                      <div className="model-report__signature-row">
                        <dt className="model-report__secondary">值类型</dt>
                        <dd>{OUTPUT_KIND_LABELS[metadata.valueKind]}</dd>
                      </div>
                      {metadata.shape !== null ? (
                        <div className="model-report__signature-row">
                          <dt className="model-report__secondary">张量形状</dt>
                          <dd className="font-mono">
                            [
                            {metadata.shape
                              .map((axis) => axis ?? "动态")
                              .join(", ")}
                            ]
                          </dd>
                        </div>
                      ) : null}
                      {metadata.dtype !== null ? (
                        <div className="model-report__signature-row">
                          <dt className="model-report__secondary">数据类型</dt>
                          <dd className="font-mono">{metadata.dtype}</dd>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </dl>
              );
            })}
          </div>
        </div>

        <dl className="model-report__opsets">
          <div className="model-report__signature-row">
            <dt className="model-report__secondary">ONNX 算子集</dt>
            <dd>
              {Object.entries(content.opsetImports)
                .map(([domain, version]) => `${domain} · ${version}`)
                .join(" / ")}
            </dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button type="button" variant="secondary" size="small">
                <Info aria-hidden="true" />
                技术校验信息
              </Button>
            </PopoverTrigger>
            <PopoverContent className="model-report__technical-details">
              <dl>
                <div>
                  <dt>内容校验值</dt>
                  <dd className="font-mono">
                    {content.modelBinary.contentHash}
                  </dd>
                </div>
                <div>
                  <dt>运行依赖</dt>
                  <dd>{content.dependencyRevisions.join(" · ")}</dd>
                </div>
              </dl>
            </PopoverContent>
          </Popover>
          {loadContent && !fixtureMode ? (
            <Button
              type="button"
              variant="primary"
              size="small"
              disabled={!canDownload || downloadState === "pending"}
              aria-busy={downloadState === "pending"}
              onClick={handleDownload}
            >
              {downloadState === "pending" ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : (
                <Download data-icon="inline-start" aria-hidden="true" />
              )}
              {downloadState === "pending"
                ? "正在下载…"
                : downloadState === "error"
                  ? "重新下载 ONNX 模型"
                  : "下载 ONNX 模型"}
            </Button>
          ) : null}
        </div>
        {fixtureMode ? (
          <p className="model-report__secondary">
            当前结果仅提供结构展示，模型文件不可部署或下载。
          </p>
        ) : null}
        {downloadState === "error" ? (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>
              模型下载失败，请检查连接后重试。
            </AlertDescription>
          </Alert>
        ) : null}
      </section>
    </article>
  );
}
