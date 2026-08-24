import type {
  DomainEntityId,
  PaperSummaryReview,
  ScientificArtifactReview,
} from "@xingwen/domain";
import type {
  DataArtifactReviewViewModel,
  EvidenceViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
} from "@xingwen/research-adapter";

import { taxonomyLabel } from "../components/scientific-content/shared";

export type ArtifactReviewForDiff =
  | DataArtifactReviewViewModel
  | PaperSummaryReview
  | PaperAcquisitionReviewViewModel
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | ScientificArtifactReview;

export type ScientificDiffCategory =
  "conclusions" | "evidence" | "relations" | "limitations";

export interface ScientificDiffItem {
  readonly key: string;
  readonly value: string;
  /** Internal semantic comparison material; never rendered to the user. */
  readonly comparisonValue?: string;
  /** Internal replacement family; never rendered to the user. */
  readonly matchGroup?: string;
  /** Full user-relevant identity without the version-bound Evidence id. */
  readonly semanticIdentity?: string;
}

export type ScientificDiffSnapshot = Readonly<
  Record<ScientificDiffCategory, readonly ScientificDiffItem[]>
>;

export interface ScientificDiffChange {
  readonly key: string;
  readonly kind: "added" | "removed" | "changed";
  readonly before: string | null;
  readonly after: string | null;
}

export interface ScientificDiffResult {
  readonly category: ScientificDiffCategory;
  readonly changes: readonly ScientificDiffChange[];
}

function item(key: string | DomainEntityId, value: string): ScientificDiffItem {
  return { key: String(key), value };
}

function evidenceLocatorLabel(locator: EvidenceViewModel["locator"]): string {
  if (locator === null) return "未提供定位";
  if (locator.kind === "paper_text") {
    return [
      locator.page === null ? null : `第 ${locator.page + 1} 页`,
      locator.section || null,
      locator.paragraph === null ? null : `第 ${locator.paragraph} 段`,
      locator.range || null,
    ]
      .filter((value): value is string => value !== null)
      .join(" · ");
  }
  if (locator.kind === "database_cell") return "数据单元格";
  if (locator.kind === "model_extraction") return "模型提取来源";
  return "推理链证据";
}

/**
 * Build Evidence changes from the existing typed Evidence read authority.
 * Technical identities participate only in matching/comparison and never in
 * the displayed before/after copy.
 */
export function buildEvidenceDiffItems(
  evidence: readonly EvidenceViewModel[],
): readonly ScientificDiffItem[] {
  return evidence.map((entry) => {
    const targetKey = `${entry.targetType}:${entry.targetId}:${entry.evidenceType}`;
    const sourceLabel = entry.source?.sourceType || "来源未公开";
    const locatorLabel = evidenceLocatorLabel(entry.locator);
    const quote = entry.quoteOrValue || "未提供可读摘录";
    const semanticIdentity = JSON.stringify({
      targetKey,
      sourceId: entry.source?.sourceId ?? null,
      sourceSnapshotId: entry.sourceSnapshotId,
      locator: entry.locator,
      quoteOrValue: entry.quoteOrValue,
    });
    return {
      key: String(entry.id),
      matchGroup: targetKey,
      semanticIdentity,
      value: `${sourceLabel} · ${locatorLabel}：${quote}`,
      comparisonValue: semanticIdentity,
    };
  });
}

function countLabel(count: number, unit: string): string {
  return count > 0 ? `${count} ${unit}` : `没有${unit}`;
}

export function buildScientificArtifactDiffSnapshot(
  review: ScientificArtifactReview,
): ScientificDiffSnapshot {
  const content = review.content;
  if (content.kind === "analysis_report") {
    return {
      conclusions: content.findings.map((finding) =>
        item(
          finding.title,
          `${finding.title}：${finding.statement || "结论说明未公开"}`,
        ),
      ),
      evidence: content.findings.map((finding) =>
        item(
          finding.title,
          `${finding.title}：${countLabel(finding.evidenceIds.length, "条证据")}`,
        ),
      ),
      relations: [],
      limitations: [...content.limitations, ...content.humanRequired].map(
        (value) => item(value, value),
      ),
    };
  }
  if (content.kind === "model_evaluation") {
    return {
      conclusions: content.metrics.map((metric) =>
        item(
          metric.label,
          `${metric.label}：${metric.value}${metric.unit ? ` ${metric.unit}` : ""}`,
        ),
      ),
      evidence: [
        item(
          "model-evidence",
          countLabel(content.evidenceIds.length, "条证据"),
        ),
      ],
      relations: [],
      limitations: content.limitations.map((value) => item(value, value)),
    };
  }
  if (content.kind === "model_artifact") {
    return {
      conclusions: [item("model", `${content.title}：${content.algorithm}`)],
      evidence: [
        item(
          "model-evidence",
          countLabel(content.evidenceIds.length, "条证据"),
        ),
      ],
      relations: [],
      limitations: content.limitations.map((value) => item(value, value)),
    };
  }
  if (content.kind === "spectrum") {
    return {
      conclusions: [
        item(
          "spectrum-summary",
          `${content.objectName}：检测到 ${content.detectedLines.length} 条谱线`,
        ),
        ...(content.radialVelocityKmS === null
          ? []
          : [
              item(
                "radial-velocity",
                `径向速度 ${content.radialVelocityKmS} km/s`,
              ),
            ]),
      ],
      evidence: [
        item(
          "spectrum-evidence",
          countLabel(content.evidenceIds.length, "条证据"),
        ),
      ],
      relations: content.detectedLines.map((line) =>
        item(
          line.lineId,
          `${taxonomyLabel(line.kind)}谱线，观测波长 ${line.observedWavelength} ${content.wavelengthUnit}`,
        ),
      ),
      limitations: [],
    };
  }
  if (content.kind === "light_curve") {
    return {
      conclusions: [
        item(
          "best-period",
          `${content.objectName}：最佳周期 ${content.bestPeriod} ${content.timeUnit}`,
        ),
      ],
      evidence: [
        item(
          "curve-evidence",
          countLabel(content.evidenceIds.length, "条证据"),
        ),
      ],
      relations: content.periodPeaks.map((peak) =>
        item(
          `period:${peak.period}`,
          `候选周期 ${peak.period}，功率 ${peak.power}`,
        ),
      ),
      limitations: [
        item(
          "rejected-samples",
          `${content.rejectedSampleCount} 个采样点未纳入分析`,
        ),
      ],
    };
  }
  return {
    conclusions: [item("visualization", content.description || content.title)],
    evidence: [
      item(
        "visualization-evidence",
        countLabel(content.evidenceIds.length, "条证据"),
      ),
    ],
    relations: [],
    limitations: [],
  };
}

export function buildLiteratureDiffSnapshot(
  review: LiteratureArtifactReviewViewModel,
): ScientificDiffSnapshot {
  if (review.kind === "literature_claims") {
    return {
      conclusions: review.claims.map((claim) =>
        item(
          claim.normalizedText || claim.text,
          `${claim.text}（${claim.status === "accepted" ? "已纳入结论" : claim.status === "rejected" ? "未纳入结论" : "仍待核验"}）`,
        ),
      ),
      evidence: review.claims.map((claim) =>
        item(
          claim.normalizedText || claim.text,
          `${claim.text}：${countLabel(claim.evidenceIds.length, "条证据")}`,
        ),
      ),
      relations: [],
      limitations: review.claims.flatMap((claim) =>
        claim.limitations.map((value) =>
          item(`${claim.normalizedText}:${value}`, `${claim.text}：${value}`),
        ),
      ),
    };
  }
  return {
    conclusions: [],
    evidence: review.relations.map((relation) =>
      item(
        relationKey(relation),
        `${relationLabel(relation)}：${countLabel(relation.evidenceIds.length, "条证据")}`,
      ),
    ),
    relations: review.relations.map((relation) =>
      item(
        relationKey(relation),
        `${relationLabel(relation)}；${relation.conditions.join("；") || "没有附加条件"}`,
      ),
    ),
    limitations: review.relations.flatMap((relation) =>
      [
        ...relation.conditionConflicts,
        ...relation.conditionUncertainties,
        ...(relation.reasoningTrace?.limitations ?? []),
        ...(relation.reasoningTrace?.conflicts ?? []),
      ].map((value) => item(`${relationKey(relation)}:${value}`, value)),
    ),
  };
}

function relationKey(
  relation: Extract<
    LiteratureArtifactReviewViewModel,
    { readonly kind: "literature_relations" }
  >["relations"][number],
): string {
  return [
    relation.sourceClaim?.normalizedText ??
      relation.sourceClaim?.text ??
      "source",
    relation.relationType,
    relation.targetClaim?.normalizedText ??
      relation.targetClaim?.text ??
      "target",
  ].join("|");
}

function relationLabel(
  relation: Extract<
    LiteratureArtifactReviewViewModel,
    { readonly kind: "literature_relations" }
  >["relations"][number],
): string {
  return `${relation.sourceClaim?.text ?? "起点论点未公开"} → ${relation.targetClaim?.text ?? "终点论点未公开"}（${taxonomyLabel(relation.relationType)}）`;
}

export function buildGraphDiffSnapshot(
  review: GraphArtifactReviewViewModel,
): ScientificDiffSnapshot {
  const labels = new Map(
    review.nodes.map((node) => [node.nodeId, node.label || "未命名研究对象"]),
  );
  const edgeLabel = (edge: GraphArtifactReviewViewModel["edges"][number]) =>
    `${edge.sourceNodeId ? (labels.get(edge.sourceNodeId) ?? "起点未公开") : "起点未公开"} → ${edge.targetNodeId ? (labels.get(edge.targetNodeId) ?? "终点未公开") : "终点未公开"}（${taxonomyLabel(edge.edgeType)}）`;
  return {
    conclusions: review.nodes.map((node) =>
      item(
        `${node.nodeType}:${node.label}`,
        `${taxonomyLabel(node.nodeType)}：${node.label}`,
      ),
    ),
    evidence: review.edges.map((edge) =>
      item(
        edgeKey(edge, labels),
        `${edgeLabel(edge)}：${countLabel(edge.evidenceIds.length, "条直接证据")}`,
      ),
    ),
    relations: review.edges.map((edge) =>
      item(edgeKey(edge, labels), edgeLabel(edge)),
    ),
    limitations:
      review.integrity.findings.length > 0
        ? [
            item(
              "integrity-findings",
              `${review.integrity.findings.length} 项关系完整性提醒`,
            ),
          ]
        : [],
  };
}

function edgeKey(
  edge: GraphArtifactReviewViewModel["edges"][number],
  labels: ReadonlyMap<DomainEntityId, string>,
): string {
  return [
    edge.sourceNodeId ? labels.get(edge.sourceNodeId) : "source",
    edge.edgeType,
    edge.targetNodeId ? labels.get(edge.targetNodeId) : "target",
  ].join("|");
}

export function buildPaperSummaryDiffSnapshot(
  review: PaperSummaryReview,
): ScientificDiffSnapshot {
  const statements = [
    ...review.background,
    ...review.methodology,
    ...review.dataset,
    ...review.experiments,
    ...review.discussion,
    ...review.researchQuestions,
  ];
  return {
    conclusions: statements.map((statement) =>
      item(statement.text, statement.text),
    ),
    evidence: statements.map((statement) =>
      item(
        statement.text,
        `${statement.text}：${countLabel(statement.evidenceIds.length, "条证据")}`,
      ),
    ),
    relations: [],
    limitations: [
      ...review.limitations.map((statement) =>
        item(statement.text, statement.text),
      ),
      ...(review.sourceConflicts.length > 0
        ? [
            item(
              "source-conflicts",
              `${review.sourceConflicts.length} 项来源版本冲突`,
            ),
          ]
        : []),
    ],
  };
}

export function buildPaperCollectionDiffSnapshot(
  review: PaperAcquisitionReviewViewModel,
): ScientificDiffSnapshot {
  return {
    conclusions: review.candidates.map((candidate) =>
      item(candidate.title, candidate.title),
    ),
    evidence: review.candidates.map((candidate) =>
      item(
        candidate.title,
        `${candidate.title}：${candidate.sourceSnapshot.sourceType}`,
      ),
    ),
    relations: [],
    limitations: review.candidates.flatMap((candidate) =>
      candidate.conflicts.map((conflict) =>
        item(
          `${candidate.title}:${conflict.field}:${conflict.detail}`,
          `${candidate.title}：${conflict.detail}`,
        ),
      ),
    ),
  };
}

export function buildDataArtifactDiffSnapshot(
  review: DataArtifactReviewViewModel,
): ScientificDiffSnapshot {
  if (review.kind === "dataset") {
    const unresolved = review.rows.reduce(
      (count, row) =>
        count + row.cells.filter((cell) => cell.status === "unresolved").length,
      0,
    );
    return {
      conclusions: review.columns.map((column) =>
        item(
          column.fieldId,
          `${column.meaningZh || column.labelEn}：${column.description}`,
        ),
      ),
      evidence: [
        item(
          "dataset-evidence",
          countLabel(review.evidenceIds.length, "条证据"),
        ),
      ],
      relations: [],
      limitations: [
        ...(review.conflictCount > 0
          ? [item("conflicts", `${review.conflictCount} 项数据冲突`)]
          : []),
        ...(unresolved > 0
          ? [item("unresolved", `${unresolved} 个数据值仍待确认`)]
          : []),
      ],
    };
  }
  if (review.kind === "field_dictionary") {
    return {
      conclusions: review.fieldDefinitions.map((field) =>
        item(
          field.fieldId,
          `${field.meaningZh || field.labelEn}：${field.description}`,
        ),
      ),
      evidence: [
        item(
          "dictionary-evidence",
          countLabel(review.evidenceIds.length, "条证据"),
        ),
      ],
      relations: [],
      limitations: [],
    };
  }
  return {
    conclusions: review.members.map((member, index) =>
      item(
        `${member.memberKind}:${index}`,
        `${taxonomyLabel(member.memberKind)}来源：${member.licenseNote}`,
      ),
    ),
    evidence: [
      item("source-evidence", countLabel(review.evidenceIds.length, "条证据")),
    ],
    relations: [],
    limitations: [
      ...(review.conflictRecordCount > 0
        ? [
            item(
              "conflicts",
              `${review.conflictRecordCount} 条来源记录存在冲突`,
            ),
          ]
        : []),
      ...(review.reviewRequiredRecordCount > 0
        ? [
            item(
              "review-required",
              `${review.reviewRequiredRecordCount} 条来源记录需要人工核验`,
            ),
          ]
        : []),
    ],
  };
}

function compareCategory(
  category: ScientificDiffCategory,
  baseline: readonly ScientificDiffItem[],
  current: readonly ScientificDiffItem[],
): ScientificDiffResult {
  const after = new Map(current.map((value) => [value.key, value]));
  const changes: ScientificDiffChange[] = [];
  const matchedBefore = new Set<string>();
  const matchedAfter = new Set<string>();

  const appendChange = (
    key: string,
    beforeItem: ScientificDiffItem | null,
    afterItem: ScientificDiffItem | null,
  ) => {
    const beforeComparison = beforeItem?.comparisonValue ?? beforeItem?.value;
    const afterComparison = afterItem?.comparisonValue ?? afterItem?.value;
    if (beforeComparison === afterComparison) return;
    changes.push({
      key,
      kind:
        beforeItem === null
          ? "added"
          : afterItem === null
            ? "removed"
            : "changed",
      before: beforeItem?.value ?? null,
      after:
        beforeItem !== null &&
        afterItem !== null &&
        beforeItem.value === afterItem.value
          ? `${afterItem.value}（来源记录已更新）`
          : (afterItem?.value ?? null),
    });
  };

  // Preserve exact internal identity when it survives within one immutable
  // version family, then match the complete scientific facts across versions.
  for (const beforeItem of baseline) {
    const exact = after.get(beforeItem.key) ?? null;
    if (exact) {
      matchedBefore.add(beforeItem.key);
      matchedAfter.add(exact.key);
      appendChange(beforeItem.key, beforeItem, exact);
    }
  }
  for (const beforeItem of baseline) {
    if (matchedBefore.has(beforeItem.key) || !beforeItem.semanticIdentity)
      continue;
    const semanticMatch = current.find(
      (value) =>
        !matchedAfter.has(value.key) &&
        value.semanticIdentity === beforeItem.semanticIdentity,
    );
    if (!semanticMatch) continue;
    matchedBefore.add(beforeItem.key);
    matchedAfter.add(semanticMatch.key);
    appendChange(beforeItem.key, beforeItem, semanticMatch);
  }

  // Pair only the remaining facts in the same scientific target family. At
  // this point unchanged reorder/prepend items are already consumed, so a pair
  // represents a real replacement rather than an ordinal coincidence.
  const unmatchedBaseline = baseline
    .filter((value) => !matchedBefore.has(value.key))
    .sort((left, right) =>
      `${left.matchGroup ?? ""}:${left.semanticIdentity ?? left.key}`.localeCompare(
        `${right.matchGroup ?? ""}:${right.semanticIdentity ?? right.key}`,
      ),
    );
  const unmatchedCurrent = current
    .filter((value) => !matchedAfter.has(value.key))
    .sort((left, right) =>
      `${left.matchGroup ?? ""}:${left.semanticIdentity ?? left.key}`.localeCompare(
        `${right.matchGroup ?? ""}:${right.semanticIdentity ?? right.key}`,
      ),
    );
  for (const beforeItem of unmatchedBaseline) {
    const replacement = unmatchedCurrent.find(
      (value) =>
        !matchedAfter.has(value.key) &&
        beforeItem.matchGroup !== undefined &&
        value.matchGroup === beforeItem.matchGroup,
    );
    if (replacement) {
      matchedBefore.add(beforeItem.key);
      matchedAfter.add(replacement.key);
      appendChange(beforeItem.key, beforeItem, replacement);
    }
  }
  for (const beforeItem of baseline) {
    if (!matchedBefore.has(beforeItem.key)) {
      appendChange(beforeItem.key, beforeItem, null);
    }
  }
  for (const afterItem of current) {
    if (!matchedAfter.has(afterItem.key)) {
      appendChange(afterItem.key, null, afterItem);
    }
  }
  return { category, changes };
}

export function compareScientificSnapshots(
  baseline: ScientificDiffSnapshot,
  current: ScientificDiffSnapshot,
): readonly ScientificDiffResult[] {
  return (["conclusions", "evidence", "relations", "limitations"] as const).map(
    (category) =>
      compareCategory(category, baseline[category], current[category]),
  );
}
