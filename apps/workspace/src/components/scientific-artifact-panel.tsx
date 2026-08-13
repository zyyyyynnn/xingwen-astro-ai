import type {
  ContentHash,
  DomainEntityId,
  ResearchArtifact,
  ScientificArtifactReview,
} from "@xingwen/domain";
import { Alert, AlertDescription, Button, Skeleton } from "@xingwen/ui";
import {
  ChartNoAxesCombined,
  Sparkles,
  Telescope,
  type LucideIcon,
} from "@xingwen/ui/icons";

import { ScientificArtifactView } from "./scientific-artifact-view";

type ScientificArtifactKind =
  "analysis_report" | "visualization" | "model_evaluation";

const KIND_LABELS: Record<ScientificArtifactKind, string> = {
  analysis_report: "分析报告",
  visualization: "科学可视化",
  model_evaluation: "模型评估",
};

function isScientificArtifact(
  artifact: ResearchArtifact,
): artifact is ResearchArtifact & { readonly kind: ScientificArtifactKind } {
  return artifact.kind in KIND_LABELS;
}

function artifactIcon(kind: ScientificArtifactKind): LucideIcon {
  if (kind === "visualization") return Telescope;
  if (kind === "analysis_report") return ChartNoAxesCombined;
  return Sparkles;
}

interface ScientificArtifactPanelProps {
  readonly artifacts: readonly ResearchArtifact[];
  readonly selectedVersionId: DomainEntityId | null;
  readonly loading: boolean;
  readonly loadError: string | null;
  readonly detailLoading: boolean;
  readonly detailError: string | null;
  readonly scientificArtifact: ScientificArtifactReview | null;
  readonly onSelect: (artifactVersionId: DomainEntityId) => void;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

export function ScientificArtifactPanel({
  artifacts,
  selectedVersionId,
  loading,
  loadError,
  detailLoading,
  detailError,
  scientificArtifact,
  onSelect,
  loadContent,
}: ScientificArtifactPanelProps) {
  const scientificArtifacts = artifacts.filter(isScientificArtifact);
  if (loading) {
    return (
      <div className="scientific-artifact-panel" aria-busy="true">
        <Skeleton className="scientific-artifact-panel__skeleton" />
      </div>
    );
  }
  if (loadError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    );
  }
  if (scientificArtifacts.length === 0) {
    return (
      <div className="artifact-view__empty">
        <p>当前运行尚未发布科学计算制品。</p>
        <p>注册 Skill 的输出通过准入与原子发布后会出现在这里。</p>
      </div>
    );
  }
  return (
    <div className="scientific-artifact-panel">
      <nav aria-label="本次运行的科学制品">
        <ul>
          {scientificArtifacts.map((artifact) => {
            const Icon = artifactIcon(artifact.kind);
            const versionId = artifact.latestVersionId;
            return (
              <li key={artifact.id}>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={versionId === null}
                  aria-current={
                    versionId === selectedVersionId ? "true" : undefined
                  }
                  onClick={() => {
                    if (versionId) onSelect(versionId);
                  }}
                >
                  <Icon aria-hidden="true" />
                  <span>
                    <strong>{artifact.title}</strong>
                    <small>{KIND_LABELS[artifact.kind]}</small>
                  </span>
                </Button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="scientific-artifact-panel__detail" aria-live="polite">
        {detailLoading ? (
          <Skeleton className="scientific-artifact-panel__detail-skeleton" />
        ) : detailError ? (
          <Alert variant="destructive">
            <AlertDescription>{detailError}</AlertDescription>
          </Alert>
        ) : scientificArtifact ? (
          <ScientificArtifactView
            artifact={scientificArtifact}
            loadContent={loadContent}
          />
        ) : null}
      </div>
    </div>
  );
}
