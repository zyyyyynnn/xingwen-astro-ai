import { useState } from "react";
import type {
  ContentHash,
  DomainEntityId,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
} from "@xingwen/domain";
import {
  Badge,
  Button,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

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

  return (
    <article
      className="scientific-artifact scientific-artifact--model-evaluation space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`模型评估报告 · ${content.algorithm} v${content.algorithmVersion}`}
          />

          <div className="model-report__facts" aria-label="模型属性">
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">任务类型</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {taskKindLabel(content.taskKind)}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">核心算法</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {content.algorithm}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">目标字段</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">训练输入</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {content.trainingInput.kind === "dataset_artifact_version"
                  ? "研究数据集"
                  : "来源快照"}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">划分策略</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {SPLIT_STRATEGY_LABELS[content.split.strategy]}
              </div>
            </div>
            {content.split.field ? (
              <div className="model-report__fact">
                <div className="text-xs text-muted-foreground">划分字段</div>
                <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                  {content.split.field}
                </div>
              </div>
            ) : null}
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">交叉验证</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {content.split.crossValidationFolds
                  ? `${content.split.crossValidationFolds} 折 CV`
                  : "单一独立测试"}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">数据源模式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </div>
            </div>
          </div>
        </>
      ) : null}

      <section className="model-report__section model-report__split">
        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">
            数据集划分比例 (Train / Val / Test Split)
          </span>
          <span>总计 100% 独立样本划分</span>
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

      {content.metrics.length > 0 ? (
        <section className="model-report__section space-y-3">
          <h4 className="text-sm font-semibold text-foreground">
            模型性能评价指标 (Evaluation Metrics)
          </h4>
          <div className="model-report__metrics">
            {content.metrics.map((metric) => {
              const baseline = content.baselineMetrics?.find(
                (b) => b.metricId === metric.metricId,
              );
              const numVal =
                typeof metric.value === "number"
                  ? metric.value
                  : Number.parseFloat(String(metric.value));
              const baselineNum = baseline
                ? typeof baseline.value === "number"
                  ? baseline.value
                  : Number.parseFloat(String(baseline.value))
                : null;
              const delta =
                baselineNum !== null &&
                !Number.isNaN(numVal) &&
                !Number.isNaN(baselineNum)
                  ? numVal - baselineNum
                  : null;

              return (
                <div key={metric.metricId} className="model-report__metric">
                  <div className="text-xs text-muted-foreground">
                    {metric.label}
                  </div>
                  <div className="mt-1 text-2xl font-bold text-foreground">
                    {formatNumber(numVal, 3)}
                    {metric.unit ? (
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        {metric.unit}
                      </span>
                    ) : null}
                  </div>
                  {delta !== null ? (
                    <div
                      className={`mt-1 text-xs ${delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}
                    >
                      {delta >= 0 ? "+" : ""}
                      {formatNumber(delta, 3)} 对比基线
                    </div>
                  ) : (
                    <div className="mt-1 text-xs text-muted-foreground">
                      测试集独立评估
                    </div>
                  )}
                  {metric.evidenceIds.length > 0 && onSelectEvidence ? (
                    <div className="mt-2">
                      <EvidenceLinks
                        evidenceIds={metric.evidenceIds}
                        onSelectEvidence={onSelectEvidence}
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      <div className="model-report__supporting-grid">
        {content.featureFields.length > 0 ? (
          <section className="model-report__section">
            <h4 className="mb-2 text-sm font-semibold text-foreground">
              输入特征字段 (Feature Input Fields)
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {content.featureFields.map((f) => (
                <Badge
                  key={f}
                  variant="secondary"
                  className="font-mono text-xs"
                >
                  {f}
                </Badge>
              ))}
            </div>
          </section>
        ) : null}

        {content.limitations.length > 0 && !enhancementOnly ? (
          <section className="model-report__section">
            <h4 className="mb-2 text-sm font-semibold text-foreground">
              模型局限性与适用边界 (Limitations)
            </h4>
            <ul className="space-y-1.5 text-xs text-muted-foreground">
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
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    if (!loadContent || content.status !== "active") return;
    try {
      setDownloading(true);
      const binary = await loadContent(content.modelBinary.contentHash);
      downloadBytes({
        bytes: binary,
        fileName: `${content.algorithm}.onnx`,
        mediaType: content.modelBinary.mediaType,
      });
    } finally {
      setDownloading(false);
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
            subtitle={`ONNX 模型交付产物包 · ${content.algorithm} v${content.algorithmVersion}`}
          />

          <div className="model-report__facts" aria-label="产物参数">
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">产物状态</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                <span className="inline-flex items-center gap-1 text-[var(--color-success)]">
                  <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
                  {content.status === "active"
                    ? "可用 (Active)"
                    : content.status}
                </span>
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">模型格式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                ONNX (Opset 17)
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">目标字段</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">输入张量</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.inputName}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">输出张量</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.outputNames.join(", ")}
              </div>
            </div>
            <div className="model-report__fact">
              <div className="text-xs text-muted-foreground">数据源模式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </div>
            </div>
          </div>
        </>
      ) : null}

      <section className="model-report__section model-report__contract">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground">
            推理张量契约规范 (ONNX I/O Signature)
          </h4>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="model-report__signature">
            <div className="text-xs font-semibold text-foreground">
              输入规格 (Inputs)
            </div>
            <div className="mt-2 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">张量名称:</span>{" "}
                <span className="font-mono font-medium">
                  {content.inputName}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">张量形状:</span>{" "}
                <span className="font-mono font-medium">
                  [{content.inputShape.map((v) => v ?? "-1").join(", ")}]
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">数据类型:</span>{" "}
                <span className="font-mono font-medium">Float32</span>
              </div>
            </div>
          </div>

          <div className="model-report__signature">
            <div className="text-xs font-semibold text-foreground">
              输出规格 (Outputs)
            </div>
            <div className="mt-2 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">张量名称:</span>{" "}
                <span className="font-mono font-medium">
                  {content.outputNames.join(", ")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">输出维度:</span>{" "}
                <span className="font-mono font-medium">
                  [-1, 2] (Softmax 概率)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">数据类型:</span>{" "}
                <span className="font-mono font-medium">Float32</span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-muted/60 px-3 py-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button type="button" variant="ghost" size="small">
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
          {loadContent ? (
            <Button
              type="button"
              variant="primary"
              size="small"
              disabled={content.status !== "active" || downloading}
              onClick={handleDownload}
            >
              <Download data-icon="inline-start" aria-hidden="true" />
              下载 ONNX 模型
            </Button>
          ) : null}
        </div>
      </section>
    </article>
  );
}
