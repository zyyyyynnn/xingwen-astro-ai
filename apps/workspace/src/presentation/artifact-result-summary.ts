import type {
  PublicArtifactPresentation,
  PublicPresentationTable,
} from "@xingwen/domain";

/**
 * Compact, kind-specific one-line scientific summary for artifact result
 * indexes. Presentation data only — no invented scientific values.
 */
export function artifactResultSummary(
  presentation: PublicArtifactPresentation,
): string | null {
  const count = (items: readonly unknown[] | undefined): number =>
    items?.length ?? 0;

  switch (presentation.kind) {
    case "dataset":
      return summarizeTable(presentation.tables?.[0] ?? null);
    case "field_dictionary":
      return `${count(presentation.entries)} 个字段定义`;
    case "source_collection":
      return `${count(presentation.entries)} 个数据来源`;
    case "paper_collection":
      return `${count(presentation.entries)} 篇文献候选`;
    case "paper_summary":
      return `${count(presentation.sections)} 个章节 · 可对照原文`;
    case "literature_claims": {
      const entries = presentation.entries ?? [];
      const candidates = entries.filter(
        (entry) => entry.status === "candidate",
      ).length;
      const base = `${entries.length} 条论断`;
      return candidates > 0 ? `${base} · ${candidates} 条待审定` : base;
    }
    case "literature_relations": {
      const entries = presentation.entries ?? [];
      const candidates = entries.filter(
        (entry) => entry.status === "candidate",
      ).length;
      return `${entries.length} 条关系 · ${candidates} 条待审定`;
    }
    case "graph":
      return `${count(presentation.graphNodes)} 个节点 · ${count(
        presentation.graphEdges,
      )} 条边`;
    case "analysis_report":
      return presentation.summary ?? null;
    default:
      return (
        summarizeTable(presentation.tables?.[0] ?? null) ??
        presentation.summary ??
        (count(presentation.entries) > 0
          ? `${count(presentation.entries)} 项内容`
          : null)
      );
  }
}

function summarizeTable(table: PublicPresentationTable | null): string | null {
  if (!table) {
    return null;
  }
  const rows = table.rows?.length ?? 0;
  const columns = table.columns?.length ?? 0;
  if (rows === 0 || columns === 0) {
    return null;
  }
  return `${rows} 行 · ${columns} 列`;
}
