import type { DomainEntityId } from "@xingwen/domain";
import type { GraphArtifactReviewViewModel } from "@xingwen/research-adapter";

import {
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";

function NodeTable({
  nodes,
  surface,
}: {
  readonly nodes: readonly GraphArtifactReviewViewModel["nodes"][number][];
  readonly surface: ScientificContentSurface;
}) {
  const visible = nodes.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--oh-border)]">
      <table className="w-full text-xs text-left border-collapse">
        <caption className="sr-only">证据关系节点</caption>
        <thead>
          <tr className="border-b bg-[var(--oh-surface-subtle)] border-[var(--oh-border)]">
            <th scope="col" className="p-2 font-medium">
              节点名称 / 标识
            </th>
            <th scope="col" className="p-2 font-medium">
              节点类别
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {visible.map((node, index) => (
            <tr
              key={node.nodeId}
              className="hover:bg-[var(--oh-surface-subtle)]"
            >
              <th
                scope="row"
                className="p-2 font-medium text-[var(--oh-foreground)]"
              >
                {node.label || `节点 ${index + 1}`}
              </th>
              <td className="p-2 text-[var(--oh-muted)]">
                {taxonomyLabel(node.nodeType)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(nodes.length, visible.length, "个节点") ? (
        <p className="p-2 text-xs text-[var(--oh-muted)] bg-[var(--oh-surface-subtle)] border-t border-[var(--oh-border)]">
          {limitNote(nodes.length, visible.length, "个节点")}
        </p>
      ) : null}
    </div>
  );
}

function EdgeTable({
  edges,
  nodeLabelById,
  surface,
}: {
  readonly edges: readonly GraphArtifactReviewViewModel["edges"][number][];
  readonly nodeLabelById: ReadonlyMap<DomainEntityId, string>;
  readonly surface: ScientificContentSurface;
}) {
  const visible = edges.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll overflow-x-auto my-2 border rounded border-[var(--oh-border)]">
      <table className="w-full text-xs text-left border-collapse">
        <caption className="sr-only">证据关系与上游证据</caption>
        <thead>
          <tr className="border-b bg-[var(--oh-surface-subtle)] border-[var(--oh-border)]">
            <th scope="col" className="p-2 font-medium">
              起止路径
            </th>
            <th scope="col" className="p-2 font-medium">
              边类别
            </th>
            <th scope="col" className="p-2 font-medium">
              证据支撑
            </th>
            <th scope="col" className="p-2 font-medium">
              关系 / 聚合详情
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {visible.map((edge) => (
            <tr
              key={edge.edgeId}
              className="hover:bg-[var(--oh-surface-subtle)]"
            >
              <td className="p-2">
                {edge.sourceNodeId && edge.targetNodeId
                  ? `${nodeLabelById.get(edge.sourceNodeId) ?? "未命名节点"} → ${nodeLabelById.get(edge.targetNodeId) ?? "未命名节点"}`
                  : "未提供节点路径"}
              </td>
              <td className="p-2">{taxonomyLabel(edge.edgeType)}</td>
              <td className="p-2">
                {edge.evidenceUseIds.length > 0
                  ? `证据使用 ${edge.evidenceUseIds.length} 条`
                  : "未提供"}
              </td>
              <td className="p-2">
                <div>
                  {edge.relation
                    ? taxonomyLabel(edge.relation.relationType)
                    : edge.dataAggregation
                      ? `聚合行 ${edge.dataAggregation.projectedRowCount}`
                      : "未提供关系明细"}
                </div>
                {edge.relationTrace ? (
                  <div className="text-xs text-[var(--oh-muted)]">
                    推导证据 {edge.relationTrace.traceEvidenceIds.length} 条
                  </div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(edges.length, visible.length, "条边") ? (
        <p className="p-2 text-xs text-[var(--oh-muted)] bg-[var(--oh-surface-subtle)] border-t border-[var(--oh-border)]">
          {limitNote(edges.length, visible.length, "条边")}
        </p>
      ) : null}
    </div>
  );
}

export function GraphContent({
  review,
  title,
  surface,
}: {
  readonly review: GraphArtifactReviewViewModel;
  readonly title: string;
  readonly surface: ScientificContentSurface;
}) {
  const nodeLabelById = new Map<DomainEntityId, string>(
    review.nodes.map((node, index) => [
      node.nodeId,
      node.label || `节点 ${index + 1}`,
    ]),
  );
  return (
    <article
      className="scientific-artifact scientific-artifact--graph"
      data-surface={surface}
    >
      <ScientificContentHeader title={title} subtitle="证据关系" />
      <div
        className="scientific-artifact__summary my-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--oh-muted)]"
        aria-label="证据关系摘要"
      >
        <span>节点 {review.nodeCount} 个</span>
        <span>边 {review.edgeCount} 条</span>
        <span>证据关联 {review.evidenceUseCount} 项</span>
      </div>
      {review.integrity.findings.length > 0 ? (
        <p className="text-xs text-[var(--oh-warning)] my-1">
          完整性提示：{review.integrity.findings[0]?.message ?? "未提供说明"}
        </p>
      ) : null}
      <section className="mt-3">
        <h4 className="mb-1 text-sm font-semibold text-[var(--oh-foreground)]">
          研究对象与论点
        </h4>
        {review.nodes.length > 0 ? (
          <NodeTable nodes={review.nodes} surface={surface} />
        ) : (
          <p className="text-xs text-[var(--oh-muted)] py-2 text-center">
            当前版本没有可展示的节点。
          </p>
        )}
      </section>
      <section className="mt-3">
        <h4 className="mb-1 text-sm font-semibold text-[var(--oh-foreground)]">
          关系
        </h4>
        {review.edges.length > 0 ? (
          <EdgeTable
            edges={review.edges}
            nodeLabelById={nodeLabelById}
            surface={surface}
          />
        ) : (
          <p className="text-xs text-[var(--oh-muted)] py-2 text-center">
            当前版本没有可展示的边。
          </p>
        )}
      </section>
    </article>
  );
}
