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

export function ModelEvaluationContent({
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

export function ModelArtifactContent({
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
      <Limitations items={content.limitations} />
    </>
  );
}
