import type {
  ArtifactKind,
  PaperSummaryReview,
  PaperSummarySupportStatus,
  SourceMode,
} from "@xingwen/domain";

const ARTIFACT_KIND_LABELS = {
  dataset: "研究数据集",
  field_dictionary: "字段说明",
  source_collection: "来源集合",
  paper_collection: "论文集合",
  paper_summary: "论文摘要",
  literature_claims: "文献论点",
  literature_relations: "文献关系",
  reasoning_traces: "推理记录",
  graph: "证据图谱",
  export: "导出文件",
} satisfies Readonly<Record<ArtifactKind, string>>;

const ARTIFACT_KIND_DESCRIPTIONS = {
  dataset: "汇总研究对象及其已标准化的关键参数。",
  field_dictionary: "解释字段含义、单位与来源映射规则。",
  source_collection: "记录本次研究使用的数据来源与可追溯快照。",
  paper_collection: "保存检索、筛选并固定下来的候选文献。",
  paper_summary: "归纳论文中的研究方法、核心发现与限制。",
  literature_claims: "提炼可以回溯到原始证据的文献论点。",
  literature_relations: "整理文献论点之间的支持、比较与关联。",
  reasoning_traces: "保留证据综合过程中的关键判断依据。",
  graph: "连接研究对象、论点、证据与来源关系。",
  export: "整理可供外部使用的研究交付文件。",
} satisfies Readonly<Record<ArtifactKind, string>>;

const SOURCE_MODE_LABELS = {
  fixture: null,
  live: "实时数据",
  cached: "缓存数据",
} satisfies Readonly<Record<SourceMode, string | null>>;

const EXECUTION_STATUS_LABELS = {
  running: "生成中",
  completed: "已完成",
  failed: "生成失败",
  rejected: "未通过",
  cancelled: "已取消",
} satisfies Readonly<
  Record<PaperSummaryReview["producerExecution"]["status"], string>
>;

const SUPPORT_STATUS_LABELS = {
  supported: "有证据支持",
  unsupported: "证据不足",
  unverifiable: "无法核验",
} satisfies Readonly<Record<PaperSummarySupportStatus, string>>;

export const ARTIFACT_CARD_COPY = {
  ariaLabel: "研究产物",
  eyebrow: "研究产物已生成",
  previous: "上一个研究产物",
  next: "下一个研究产物",
  openReport: "查看完整报告",
  generated: "已生成",
  waiting: "等待生成",
  originalPaper: "原始论文",
  keyFinding: "核心结论",
  description: "产物说明",
  missingFinding: "未生成可展示的核心发现。",
  missingContent: "该产物尚未生成可读取内容。",
  position(index: number, total: number): string {
    return `第 ${index} 项，共 ${total} 项`;
  },
  unsupportedDescription(reason: string): string {
    return `${reason}该产物已保留在本次研究结果中，可在后续能力开放后查看。`;
  },
} as const;

export function artifactKindLabel(kind: ArtifactKind): string {
  return ARTIFACT_KIND_LABELS[kind];
}

export function artifactKindDescription(kind: ArtifactKind): string {
  return ARTIFACT_KIND_DESCRIPTIONS[kind];
}

export function sourceModeLabel(sourceMode: SourceMode): string | null {
  return SOURCE_MODE_LABELS[sourceMode];
}

export function executionStatusLabel(
  status: PaperSummaryReview["producerExecution"]["status"],
): string {
  return EXECUTION_STATUS_LABELS[status];
}

export function supportStatusLabel(status: PaperSummarySupportStatus): string {
  return SUPPORT_STATUS_LABELS[status];
}
