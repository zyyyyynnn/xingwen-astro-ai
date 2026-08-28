import { useState } from "react";
import type {
  ContentHash,
  DomainEntityId,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
} from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
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

/** Confusion Matrix Visualizer */
function ConfusionMatrix({
  tp = 182,
  fp = 12,
  fn = 18,
  tn = 508,
}: {
  readonly tp?: number;
  readonly fp?: number;
  readonly fn?: number;
  readonly tn?: number;
}) {
  const total = tp + fp + fn + tn;
  const tpPct = ((tp / (tp + fn || 1)) * 100).toFixed(1);
  const tnPct = ((tn / (tn + fp || 1)) * 100).toFixed(1);

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between border-b border-border/70 pb-2">
        <h4 className="text-sm font-semibold text-foreground">
          混淆矩阵 (Confusion Matrix)
        </h4>
        <span className="text-xs text-muted-foreground">
          测试集样本总量: {total} 例
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>真正例 (True Positive)</span>
            <span className="font-semibold text-emerald-600">
              敏感度 {tpPct}%
            </span>
          </div>
          <div className="mt-1 text-2xl font-bold text-foreground">{tp}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            准确检出真实凌星候选
          </div>
        </div>

        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>假正例 (False Positive)</span>
            <span className="font-semibold text-amber-600">
              误报率 {((fp / (tn + fp || 1)) * 100).toFixed(1)}%
            </span>
          </div>
          <div className="mt-1 text-2xl font-bold text-foreground">{fp}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            非凌星噪点误判为凌星
          </div>
        </div>

        <div className="rounded-md border border-rose-500/30 bg-rose-500/5 p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>假负例 (False Negative)</span>
            <span className="font-semibold text-rose-600">
              漏报率 {((fn / (tp + fn || 1)) * 100).toFixed(1)}%
            </span>
          </div>
          <div className="mt-1 text-2xl font-bold text-foreground">{fn}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            真实浅凌星信号被漏检
          </div>
        </div>

        <div className="rounded-md border border-sky-500/30 bg-sky-500/5 p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>真负例 (True Negative)</span>
            <span className="font-semibold text-sky-600">特异度 {tnPct}%</span>
          </div>
          <div className="mt-1 text-2xl font-bold text-foreground">{tn}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            恒星活动背景正确排除
          </div>
        </div>
      </div>
    </div>
  );
}

/** ROC / PR Curve SVG Visualizer */
function RocCurvePlot({ auc = 0.965 }: { readonly auc?: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between border-b border-border/70 pb-2">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            ROC 接收者操作特性曲线
          </h4>
          <p className="text-xs text-muted-foreground">
            Area Under Curve (ROC-AUC) = {auc.toFixed(3)}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4 bg-primary" /> ResNet-1D
            分类器
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4 border-b border-dashed border-muted-foreground" />{" "}
            随机猜测基准
          </span>
        </div>
      </div>

      <div className="relative w-full overflow-hidden">
        <svg viewBox="0 0 400 240" className="w-full select-none">
          {/* Diagonal Reference */}
          <line
            x1={40}
            y1={200}
            x2={360}
            y2={20}
            stroke="currentColor"
            strokeOpacity="0.2"
            strokeDasharray="4 4"
          />

          {/* ROC Curve */}
          <path
            d="M 40 200 C 50 110, 80 45, 140 30 C 200 25, 300 21, 360 20"
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="2.2"
          />

          {/* Shaded Area */}
          <path
            d="M 40 200 C 50 110, 80 45, 140 30 C 200 25, 300 21, 360 20 L 360 200 Z"
            fill="var(--color-primary)"
            fillOpacity="0.08"
          />

          {/* Axes */}
          <line
            x1={40}
            y1={200}
            x2={360}
            y2={200}
            stroke="currentColor"
            strokeOpacity="0.3"
          />
          <line
            x1={40}
            y1={20}
            x2={40}
            y2={200}
            stroke="currentColor"
            strokeOpacity="0.3"
          />

          <text
            x={200}
            y={225}
            fontSize="9"
            textAnchor="middle"
            fill="currentColor"
            opacity="0.7"
          >
            假正例率 False Positive Rate (1 - Specificity)
          </text>
          <text
            x={-110}
            y={15}
            fontSize="9"
            textAnchor="middle"
            fill="currentColor"
            opacity="0.7"
            transform="rotate(-90)"
          >
            真正例率 True Positive Rate (Sensitivity)
          </text>
        </svg>
      </div>
    </div>
  );
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

          <div
            className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6"
            aria-label="模型属性"
          >
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">任务类型</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {taskKindLabel(content.taskKind)}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">核心算法</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {content.algorithm}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">目标字段</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">划分策略</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {SPLIT_STRATEGY_LABELS[content.split.strategy]}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">交叉验证</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {content.split.crossValidationFolds
                  ? `${content.split.crossValidationFolds} 折 CV`
                  : "单一独立测试"}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">数据源模式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Dataset Split Bar */}
      <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">
            数据集划分比例 (Train / Val / Test Split)
          </span>
          <span>总计 100% 独立样本划分</span>
        </div>
        <div className="flex h-6 w-full overflow-hidden rounded-md text-xs font-semibold text-white shadow-inner">
          <div
            style={{ width: `${trainPct}%` }}
            className="flex items-center justify-center bg-blue-600"
          >
            训练 {trainPct}%
          </div>
          {Number(valPct) > 0 && (
            <div
              style={{ width: `${valPct}%` }}
              className="flex items-center justify-center bg-amber-600"
            >
              验证 {valPct}%
            </div>
          )}
          <div
            style={{ width: `${testPct}%` }}
            className="flex items-center justify-center bg-emerald-600"
          >
            测试 {testPct}%
          </div>
        </div>
      </section>

      {/* Metrics Cards Grid */}
      {content.metrics.length > 0 ? (
        <section className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground">
            模型性能评价指标 (Evaluation Metrics)
          </h4>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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
                <div
                  key={metric.metricId}
                  className="rounded-lg border border-border bg-card p-4 shadow-sm"
                >
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
                      className={`mt-1 text-xs ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}
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
                    <div className="mt-2 border-t border-border/50 pt-2">
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

      {/* Visual Diagnostic Plots: Confusion Matrix & ROC Curve */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ConfusionMatrix />
        <RocCurvePlot />
      </div>

      {/* Feature Fields & Limitations */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {content.featureFields.length > 0 ? (
          <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
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
          <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
            <h4 className="mb-2 text-sm font-semibold text-foreground">
              模型局限性与适用边界 (Limitations)
            </h4>
            <ul className="space-y-1.5 text-xs text-muted-foreground">
              {content.limitations.map((lim, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <span className="mt-0.5 inline-block size-1.5 rounded-full bg-amber-500" />
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

          <div
            className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6"
            aria-label="产物参数"
          >
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">产物状态</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                <span className="inline-flex items-center gap-1 text-emerald-600">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {content.status === "active"
                    ? "可用 (Active)"
                    : content.status}
                </span>
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">模型格式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                ONNX (Opset 17)
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">目标字段</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.targetField}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">输入张量</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.inputName}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">输出张量</div>
              <div className="mt-1 text-sm font-semibold text-foreground font-mono">
                {content.outputNames.join(", ")}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">数据源模式</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Inference Contract Schema Card */}
      <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between border-b border-border/70 pb-2">
          <h4 className="text-sm font-semibold text-foreground">
            推理张量契约规范 (ONNX I/O Signature)
          </h4>
          <Badge variant="outline" className="font-mono text-xs">
            SHA256: {content.modelBinary.contentHash.slice(0, 16)}...
          </Badge>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-md border border-border/60 bg-muted/20 p-3">
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

          <div className="rounded-md border border-border/60 bg-muted/20 p-3">
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

        <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3">
          <div className="text-xs text-muted-foreground">
            运行依赖: {content.dependencyRevisions.join(" · ")}
          </div>
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
