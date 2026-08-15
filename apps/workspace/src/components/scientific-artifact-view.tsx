import type {
  ContentHash,
  DomainEntityId,
  ScientificArtifactReview,
  VisualizationReviewContent,
} from "@xingwen/domain";
import { Button } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

import { downloadBytes } from "../presentation/browser-download";
import { EvidenceLinks } from "./evidence-links";
import { ScientificChart } from "./scientific-chart";
import { AnalysisReportContent } from "./scientific-content/analysis-report-content";
import {
  ModelArtifactContent,
  ModelEvaluationContent,
} from "./scientific-content/model-evaluation-content";
import { WwtViewport } from "./wwt-viewport";

const SOURCE_MODE_LABELS: Record<string, string> = {
  live: "实时数据",
  cached: "缓存数据",
  demo: "演示数据",
};

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
                  fileName: "fits-image.fits",
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
        <p className="artifact-view__source-mode">
          {SOURCE_MODE_LABELS[artifact.sourceMode] ?? artifact.sourceMode}
          {artifact.evidence.length > 0
            ? ` · 证据 ${artifact.evidence.length}`
            : ""}
        </p>
      </header>
      {content.kind === "analysis_report" ? (
        <AnalysisReportContent
          content={content}
          onSelectEvidence={onSelectEvidence}
        />
      ) : content.kind === "model_evaluation" ? (
        <ModelEvaluationContent
          content={content}
          onSelectEvidence={onSelectEvidence}
        />
      ) : content.kind === "model_artifact" ? (
        <ModelArtifactContent content={content} loadContent={loadContent} />
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
            <dt>生产者</dt>
            <dd>
              {artifact.producerExecution.producerName} ·{" "}
              {artifact.producerExecution.producerVersion}
            </dd>
          </div>
        </dl>
        {artifact.sourceSnapshots.map((snapshot) => (
          <p key={snapshot.id}>
            {snapshot.sourceId} · {snapshot.licenseNote}
          </p>
        ))}
      </details>
    </article>
  );
}
