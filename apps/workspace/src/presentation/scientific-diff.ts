import type {
  ArtifactKind,
  DomainEntityId,
  JsonValue,
  PaperSummaryReview,
  ScientificArtifactReview,
  SourceSnapshotSummary,
} from "@xingwen/domain";
import type {
  ContractInputViewModel,
  DataArtifactReviewViewModel,
  EvidenceViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
} from "@xingwen/research-adapter";

import { taxonomyLabel } from "../components/scientific-content/shared";
import { artifactKindLabel } from "./artifact-presentation-labels";

export type ArtifactReviewForDiff =
  | DataArtifactReviewViewModel
  | PaperSummaryReview
  | PaperAcquisitionReviewViewModel
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | ScientificArtifactReview;

type ArtifactContentDiffCategory =
  "conclusions" | "evidence" | "relations" | "limitations";

export type ScientificDiffCategory =
  ArtifactContentDiffCategory | "contract" | "sources";

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
  Record<ArtifactContentDiffCategory, readonly ScientificDiffItem[]> &
    Partial<Record<"contract" | "sources", readonly ScientificDiffItem[]>>
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

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;

function readableIdentity(value: string, hiddenFallback: string): string {
  const taxonomy = taxonomyLabel(value);
  if (taxonomy !== "其他") return taxonomy;
  if (UUID_PATTERN.test(value)) return hiddenFallback;
  return value.replaceAll(/[_-]+/gu, " ");
}

function readableList(
  values: readonly string[],
  hiddenFallback: string,
): string {
  if (values.length === 0) return "未指定";
  return [...values]
    .map((value) => readableIdentity(value, hiddenFallback))
    .sort((left, right) => left.localeCompare(right, "zh-Hans"))
    .join("、");
}

function semanticList(values: readonly string[]): string {
  return [...values].sort().join("\u001f");
}

function typedParameterValue(value: JsonValue): string {
  if (value === null) return "未设置";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(typedParameterValue).join("、");
  }
  return Object.entries(value)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(
      ([key, entry]) =>
        `${readableIdentity(key, "参数")}：${typedParameterValue(entry)}`,
    )
    .join("；");
}

function contractItem(
  key: string,
  value: string,
  comparisonValue = value,
): ScientificDiffItem {
  return { key, value, comparisonValue };
}

/** Typed projection of the immutable Research Contract for Scientific Diff. */
export function buildContractDiffItems(
  contract: ContractInputViewModel,
): readonly ScientificDiffItem[] {
  const tasks = contract.scientificTasks.map((task) => {
    const parameters = Object.entries(task.parameters)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(
        ([key, value]) =>
          `${readableIdentity(key, "参数")}：${typedParameterValue(value)}`,
      );
    const skill = readableIdentity(task.skillId, "科研任务");
    const display = [skill, ...parameters].join("；");
    const comparisonValue = [
      task.skillId,
      ...Object.entries(task.parameters)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, value]) => `${key}=${typedParameterValue(value)}`),
      `inputs=${semanticList(task.inputRefs)}`,
    ].join("\u001f");
    return {
      key: `scientific-task:${String(task.taskId)}`,
      matchGroup: `scientific-task:${task.skillId}`,
      semanticIdentity: comparisonValue,
      value: `科研任务：${display}`,
      comparisonValue,
    } satisfies ScientificDiffItem;
  });

  const outputs = contract.outputRequirements.map((kind: ArtifactKind) =>
    artifactKindLabel(kind),
  );
  return [
    contractItem("research-goal", `研究目标：${contract.researchGoal}`),
    contractItem(
      "target-objects",
      `研究对象：${readableList(contract.targetObjects, "已选研究对象")}`,
      semanticList(contract.targetObjects),
    ),
    contractItem(
      "requested-fields",
      `研究字段：${readableList(contract.requestedFields, "已选研究字段")}`,
      semanticList(contract.requestedFields),
    ),
    contractItem(
      "source-scope",
      `允许来源：${readableList(contract.sourceScope.allowedSources, "已选来源")}`,
      semanticList(contract.sourceScope.allowedSources),
    ),
    contractItem(
      "paper-keywords",
      `论文关键词：${readableList(contract.paperSearchScope.keywords, "关键词")}`,
      semanticList(contract.paperSearchScope.keywords),
    ),
    contractItem(
      "paper-years",
      `论文年份：${contract.paperSearchScope.yearFrom ?? "不限"} 至 ${contract.paperSearchScope.yearTo ?? "不限"}`,
      `${contract.paperSearchScope.yearFrom ?? ""}:${contract.paperSearchScope.yearTo ?? ""}`,
    ),
    contractItem(
      "paper-sources",
      `论文来源：${readableList(contract.paperSearchScope.sourceIds, "已选论文来源")}`,
      semanticList(contract.paperSearchScope.sourceIds),
    ),
    contractItem(
      "paper-limit",
      `候选论文上限：${contract.paperSearchScope.maxCandidates}`,
    ),
    ...tasks,
    contractItem(
      "requested-outputs",
      `交付结果：${[...outputs].sort().join("、")}`,
      semanticList(contract.outputRequirements),
    ),
    contractItem(
      "evidence-requirements",
      `证据要求：${contract.evidenceRequirements.requireLocator ? "需要定位" : "不要求定位"}；${contract.evidenceRequirements.requireSourceSnapshot ? "需要来源快照" : "不要求来源快照"}；最低覆盖率 ${Math.round(contract.evidenceRequirements.minimumCoverage * 100)}%`,
      [
        contract.evidenceRequirements.requireLocator,
        contract.evidenceRequirements.requireSourceSnapshot,
        contract.evidenceRequirements.minimumCoverage,
      ].join(":"),
    ),
    contractItem(
      "quality-constraints",
      `质量约束：来源完整度至少 ${Math.round(contract.qualityConstraints.sourceCompletenessMin * 100)}%；单位一致性至少 ${Math.round(contract.qualityConstraints.unitConsistencyMin * 100)}%`,
      `${contract.qualityConstraints.sourceCompletenessMin}:${contract.qualityConstraints.unitConsistencyMin}`,
    ),
    contractItem(
      "unit-policy",
      `单位规则：${contract.dataRequirements.unitPolicy === "canonical" ? "统一为标准单位" : "按研究约定"}`,
      contract.dataRequirements.unitPolicy,
    ),
    contractItem(
      "document-source-policy",
      `研究文档：${contract.dataRequirements.documentSourcePolicy === "research_input" ? "允许作为来源" : "不作为来源"}`,
      contract.dataRequirements.documentSourcePolicy,
    ),
  ];
}

function sourceSnapshotLabel(snapshot: SourceSnapshotSummary): string {
  const sourceName = readableIdentity(snapshot.sourceId, "已授权来源");
  const retrieved = new Date(snapshot.retrievedAt);
  const retrievedLabel = Number.isNaN(retrieved.getTime())
    ? snapshot.retrievedAt
    : retrieved.toLocaleString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
  return `${readableIdentity(snapshot.sourceType, "科研来源")} · ${sourceName}；获取于 ${retrievedLabel}；${snapshot.licenseNote || "许可信息未提供"}`;
}

/** Version-bound Source Set; hashes and machine ids stay comparison-only. */
export function buildSourceSetDiffItems(
  snapshots: readonly SourceSnapshotSummary[],
): readonly ScientificDiffItem[] {
  return snapshots.map((snapshot) => {
    const semanticIdentity = [
      snapshot.id,
      snapshot.sourceId,
      snapshot.sourceType,
      snapshot.contentHash,
      snapshot.queryHash,
      snapshot.retrievedAt,
    ].join("\u001f");
    return {
      key: String(snapshot.id),
      value: sourceSnapshotLabel(snapshot),
      comparisonValue: semanticIdentity,
      semanticIdentity,
      matchGroup: `source:${snapshot.sourceId}`,
    };
  });
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
  return (
    [
      "contract",
      "sources",
      "conclusions",
      "evidence",
      "relations",
      "limitations",
    ] as const
  ).map((category) =>
    compareCategory(
      category,
      baseline[category] ?? [],
      current[category] ?? [],
    ),
  );
}
