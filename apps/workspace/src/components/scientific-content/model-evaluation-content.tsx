import type {
  ContentHash,
  DomainEntityId,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
} from "@xingwen/domain";
import { Button } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

import { downloadBytes } from "../../presentation/browser-download";
import { Limitations, Metrics } from "./analysis-report-content";
import {
  ScientificContentHeader,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

const TASK_KIND_LABELS: Record<string, string> = {
  classification: "分类",
  regression: "回归",
  forecast: "预测",
  image_classification: "图像分类",
  time_series_classification: "时间序列分类",
};

const SPLIT_STRATEGY_LABELS: Record<
  ModelEvaluationReviewContent["split"]["strategy"],
  string
> = {
  random: "随机划分",
  stratified: "分层划分",
  group: "分组划分",
  entity: "实体隔离划分",
  time: "时间顺序划分",
};

function taskKindLabel(value: string): string {
  return TASK_KIND_LABELS[value] ?? "其他任务";
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
  return (
    <article
      className="scientific-artifact scientific-artifact--model-evaluation"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <ScientificContentHeader
          title={content.title || title}
          subtitle={`模型评估 · ${sourceModeLabel(sourceMode)}`}
        />
      ) : null}
      {!enhancementOnly ? (
        <dl className="model-evaluation__identity">
          <div>
            <dt>任务</dt>
            <dd>{taskKindLabel(content.taskKind)}</dd>
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
      ) : null}
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
        {!enhancementOnly ? (
          <p>
            {SPLIT_STRATEGY_LABELS[content.split.strategy]}
            {content.split.field === null
              ? ""
              : ` · 划分字段 ${content.split.field}`}
            {content.split.randomSeed === null
              ? " · 无随机种子"
              : ` · 随机种子 ${content.split.randomSeed}`}
            {content.split.crossValidationFolds === null
              ? " · 未执行交叉验证"
              : ` · ${content.split.crossValidationFolds} 折交叉验证`}
            {content.split.trainCutoff === null
              ? ""
              : ` · 训练截止 ${content.split.trainCutoff}`}
          </p>
        ) : null}
      </section>
      {!enhancementOnly ? (
        <Metrics
          metrics={content.metrics}
          baseline={content.baselineMetrics}
          onSelectEvidence={onSelectEvidence}
        />
      ) : null}
      {!enhancementOnly ? (
        <section className="model-evaluation__features">
          <h4>特征字段</h4>
          <p>{content.featureFields.join("、")}</p>
        </section>
      ) : null}
      {!enhancementOnly ? <Limitations items={content.limitations} /> : null}
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
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly enhancementOnly?: boolean;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--model-artifact"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <ScientificContentHeader
          title={content.title || title}
          subtitle={`模型产物 · ${sourceModeLabel(sourceMode)}`}
        />
      ) : null}
      {!enhancementOnly ? (
        <dl className="model-evaluation__identity">
          <div>
            <dt>状态</dt>
            <dd>{content.status}</dd>
          </div>
          <div>
            <dt>任务</dt>
            <dd>{taskKindLabel(content.taskKind)}</dd>
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
      ) : null}
      {!enhancementOnly ? (
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
                {content.inputShape
                  .map((value) => value ?? "batch")
                  .join(" × ")}
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
      ) : null}
      {!enhancementOnly ? (
        <section className="model-evaluation__features">
          <h4>运行依赖</h4>
          <p>{content.dependencyRevisions.join(" · ")}</p>
        </section>
      ) : null}
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
                fileName: `${content.algorithm}.onnx`,
                mediaType: content.modelBinary.mediaType,
              }),
            )
          }
        >
          <Download data-icon="inline-start" aria-hidden="true" />
          下载 ONNX 模型
        </Button>
      </div>
      {!enhancementOnly ? <Limitations items={content.limitations} /> : null}
    </article>
  );
}
