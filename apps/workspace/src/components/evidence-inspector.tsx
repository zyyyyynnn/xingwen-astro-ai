import { useQuery } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import type {
  EvidenceLocatorViewModel,
  EvidenceViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Separator,
  Skeleton,
} from "@xingwen/ui";
import { ChevronLeft, X } from "@xingwen/ui/icons";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

function Locator({
  locator,
}: {
  readonly locator: EvidenceLocatorViewModel | null;
}) {
  if (locator === null) return <p>当前证据未提供可定位信息。</p>;
  switch (locator.kind) {
    case "database_cell":
      return (
        <dl>
          <div>
            <dt>查询</dt>
            <dd>{locator.queryHash}</dd>
          </div>
          <div>
            <dt>行</dt>
            <dd>{locator.rowKey}</dd>
          </div>
          <div>
            <dt>字段</dt>
            <dd>{locator.field}</dd>
          </div>
        </dl>
      );
    case "paper_text":
      return (
        <dl>
          <div>
            <dt>章节</dt>
            <dd>{locator.section}</dd>
          </div>
          <div>
            <dt>页码</dt>
            <dd>{locator.page ?? "未提供"}</dd>
          </div>
          <div>
            <dt>段落</dt>
            <dd>{locator.paragraph ?? "未提供"}</dd>
          </div>
          <div>
            <dt>范围</dt>
            <dd>{locator.range ?? "未提供"}</dd>
          </div>
        </dl>
      );
    case "model_extraction":
      return (
        <dl>
          <div>
            <dt>输入证据</dt>
            <dd>{locator.inputEvidenceId}</dd>
          </div>
          <div>
            <dt>Prompt</dt>
            <dd>{locator.promptName}</dd>
          </div>
          <div>
            <dt>模型版本</dt>
            <dd>{locator.modelVersion}</dd>
          </div>
        </dl>
      );
    case "reasoning_trace":
      return (
        <dl>
          <div>
            <dt>关系</dt>
            <dd>{locator.relationId}</dd>
          </div>
          <div>
            <dt>步骤</dt>
            <dd>{locator.stepKey}</dd>
          </div>
        </dl>
      );
    case "scientific_computation":
      return (
        <dl>
          <div>
            <dt>任务</dt>
            <dd>{locator.taskId}</dd>
          </div>
          <div>
            <dt>技能</dt>
            <dd>{locator.skillId}</dd>
          </div>
          <div>
            <dt>输出</dt>
            <dd>{locator.outputHash}</dd>
          </div>
          <div>
            <dt>上游证据</dt>
            <dd>{locator.upstreamEvidenceIds.length || "未提供"}</dd>
          </div>
        </dl>
      );
  }
}

function EvidenceContent({
  evidence,
}: {
  readonly evidence: EvidenceViewModel;
}) {
  return (
    <div className="evidence-inspector__content">
      <div className="evidence-inspector__badges">
        <Badge variant="secondary">{evidence.evidenceType}</Badge>
        <Badge variant="outline">
          可信度 {Math.round(evidence.confidence * 100)}%
        </Badge>
      </div>
      <dl className="evidence-inspector__identity">
        <div>
          <dt>目标</dt>
          <dd>
            {evidence.targetType} · {evidence.targetId}
          </dd>
        </div>
        <div>
          <dt>产物版本</dt>
          <dd>{evidence.artifactVersionId}</dd>
        </div>
        <div>
          <dt>来源快照</dt>
          <dd>{evidence.sourceSnapshotId ?? "未提供"}</dd>
        </div>
        <div>
          <dt>抽取方法</dt>
          <dd>{evidence.extractionMethod}</dd>
        </div>
      </dl>
      <Separator />
      <section>
        <h3>引用值</h3>
        <blockquote>
          {evidence.quoteOrValue ?? "当前证据未提供引用值。"}
        </blockquote>
      </section>
      <section className="evidence-inspector__locator">
        <h3>定位信息</h3>
        <Locator locator={evidence.locator} />
      </section>
    </div>
  );
}

export function EvidenceInspector({
  runtime,
  projectId,
  evidenceId,
  canGoBack,
  onBack,
  onClose,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly evidenceId: DomainEntityId | null;
  readonly canGoBack: boolean;
  readonly onBack: () => void;
  readonly onClose: () => void;
}) {
  const query = useQuery({
    ...runtime.application.queries.evidence(projectId, evidenceId ?? projectId),
    enabled: evidenceId !== null,
  });
  return (
    <Dialog
      open={evidenceId !== null}
      onOpenChange={(open) => !open && onClose()}
    >
      <DialogContent
        className="evidence-inspector"
        aria-describedby="evidence-inspector-description"
      >
        <DialogHeader>
          <DialogTitle>证据核验</DialogTitle>
          <DialogDescription id="evidence-inspector-description">
            独立读取已固定 ArtifactVersion 的证据、来源与 locator。
          </DialogDescription>
        </DialogHeader>
        <div className="evidence-inspector__toolbar">
          <Button
            type="button"
            variant="ghost"
            size="small"
            disabled={!canGoBack}
            onClick={onBack}
          >
            <ChevronLeft data-icon="inline-start" aria-hidden="true" />
            返回上一条
          </Button>
          <Button type="button" variant="ghost" size="small" onClick={onClose}>
            <X data-icon="inline-start" aria-hidden="true" />
            关闭
          </Button>
        </div>
        {query.isPending ? (
          <div
            className="evidence-inspector__loading"
            aria-busy="true"
            aria-label="正在读取证据"
          >
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </div>
        ) : query.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              {
                runtime.researchAdapter.toPublicApplicationError(query.error)
                  .safeMessage
              }
            </AlertDescription>
          </Alert>
        ) : (
          <EvidenceContent evidence={query.data} />
        )}
      </DialogContent>
    </Dialog>
  );
}
