import type {
  RepairAction,
  RepairCheckpointContext,
  RepairDecisionInput,
  RepairOutcome,
} from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Button,
  RadioGroup,
  RadioGroupItem,
  Textarea,
} from "@xingwen/ui";
import { useState } from "react";

const ACTION_LABELS: Readonly<Record<RepairAction, string>> = {
  accepted: "接受候选匹配",
  rejected: "拒绝候选匹配",
  keep_unresolved: "保留未决，暂不合并",
};

interface DraftDecision {
  readonly action: RepairAction | null;
  readonly rationale: string;
}

export function ScientificRepairPrompt({
  id,
  question,
  context,
  decisions,
  outcome,
  answered,
  isSubmitting = false,
  onSubmit,
}: {
  readonly id: string;
  readonly question: string;
  readonly context: RepairCheckpointContext;
  readonly decisions: readonly RepairDecisionInput[];
  readonly outcome: RepairOutcome | null;
  readonly answered: boolean;
  readonly isSubmitting?: boolean;
  readonly onSubmit: (decisions: readonly RepairDecisionInput[]) => void;
}) {
  const existing = new Map(
    decisions.map((decision) => [decision.defectId, decision]),
  );
  const [drafts, setDrafts] = useState<Readonly<Record<string, DraftDecision>>>(
    () =>
      Object.fromEntries(
        context.defects.map((defect) => {
          const decision = existing.get(defect.defectId);
          return [
            defect.defectId,
            {
              action: decision?.action ?? null,
              rationale: decision?.rationale ?? "",
            },
          ];
        }),
      ),
  );
  const complete = context.defects.every((defect) => {
    const draft = drafts[defect.defectId];
    return Boolean(draft?.action) && Boolean(draft?.rationale.trim());
  });

  return (
    <section
      className="scientific-repair"
      aria-labelledby={`${id}-title`}
      data-testid={`scientific-repair-${answered ? "answered" : "active"}`}
    >
      <h3 id={`${id}-title`} className="scientific-repair__title">
        {question}
      </h3>
      <p className="scientific-repair__description">
        每项决定都会绑定当前规则集、输入和证据，并在同一研究运行中重新计算与校验。
      </p>
      <ol className="scientific-repair__defects">
        {context.defects.map((defect, index) => {
          const draft = drafts[defect.defectId] ?? {
            action: null,
            rationale: "",
          };
          return (
            <li key={defect.defectId} className="scientific-repair__defect">
              <div className="scientific-repair__defect-heading">
                <span>冲突 {index + 1}</span>
                <span>{defect.evidence.length} 条匹配证据</span>
              </div>
              <dl className="scientific-repair__candidates">
                <div>
                  <dt>左侧候选</dt>
                  <dd>{defect.leftCandidateIds.join("、")}</dd>
                </div>
                <div>
                  <dt>右侧候选</dt>
                  <dd>{defect.rightCandidateIds.join("、")}</dd>
                </div>
              </dl>
              <ul className="scientific-repair__evidence" aria-label="匹配证据">
                {defect.evidence.map((evidence) => (
                  <li key={evidence.evidenceId}>
                    <span>{evidence.summary}</span>
                    <span>置信度 {Math.round(evidence.confidence * 100)}%</span>
                  </li>
                ))}
              </ul>
              <RadioGroup
                value={draft.action ?? ""}
                disabled={answered}
                className="scientific-repair__actions"
                onValueChange={(value) =>
                  setDrafts((current) => ({
                    ...current,
                    [defect.defectId]: {
                      ...draft,
                      action: value as RepairAction,
                    },
                  }))
                }
              >
                {context.ruleSet.allowedActions.map((action) => {
                  const controlId = `${id}-${defect.defectId}-${action}`;
                  return (
                    <label key={action} htmlFor={controlId}>
                      <RadioGroupItem id={controlId} value={action} />
                      <span>{ACTION_LABELS[action]}</span>
                    </label>
                  );
                })}
              </RadioGroup>
              <Textarea
                value={draft.rationale}
                disabled={answered}
                aria-label={`冲突 ${index + 1} 的决定理由`}
                placeholder="说明判断依据（必填）"
                onChange={(event) =>
                  setDrafts((current) => ({
                    ...current,
                    [defect.defectId]: {
                      ...draft,
                      rationale: event.target.value,
                    },
                  }))
                }
              />
            </li>
          );
        })}
      </ol>
      {outcome ? (
        <Alert
          variant={outcome.status === "revalidated" ? "default" : "destructive"}
        >
          <AlertDescription>
            {outcome.status === "revalidated"
              ? `已通过重验证：解决 ${outcome.resolvedDefectIds.length} 项，保留未决 ${outcome.unresolvedDefectIds.length} 项。`
              : "提交的修复未通过确定性重验证，未发布修复后的数据产物。"}
          </AlertDescription>
        </Alert>
      ) : null}
      {!answered ? (
        <div className="scientific-repair__submit">
          <Button
            size="small"
            disabled={!complete || isSubmitting}
            onClick={() =>
              onSubmit(
                context.defects.map((defect) => {
                  const draft = drafts[defect.defectId];
                  if (!draft?.action)
                    throw new Error("repair decision is incomplete");
                  return {
                    defectId: defect.defectId,
                    action: draft.action,
                    rationale: draft.rationale.trim(),
                  };
                }),
              )
            }
          >
            {isSubmitting ? "正在提交..." : "提交全部修复决定"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
