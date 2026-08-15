import type { DomainEntityId } from "@xingwen/domain";
import type { GraphArtifactReviewViewModel } from "@xingwen/research-adapter";

import {
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
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
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">证据图谱节点</caption>
        <thead>
          <tr>
            <th scope="col">节点</th>
            <th scope="col">类型</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((node, index) => (
            <tr key={node.nodeId}>
              <th scope="row">{node.label || `节点 ${index + 1}`}</th>
              <td>{taxonomyLabel(node.nodeType)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(nodes.length, visible.length, "个节点") ? (
        <p className="scientific-artifact__table-note">
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
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">证据图谱边与上游证据</caption>
        <thead>
          <tr>
            <th scope="col">边</th>
            <th scope="col">路径</th>
            <th scope="col">类型</th>
            <th scope="col">证据使用</th>
            <th scope="col">关系 / 聚合</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((edge, index) => (
            <tr key={edge.edgeId}>
              <th scope="row">{`边 ${index + 1}`}</th>
              <td>
                {edge.sourceNodeId && edge.targetNodeId
                  ? `${nodeLabelById.get(edge.sourceNodeId) ?? "未命名节点"} → ${nodeLabelById.get(edge.targetNodeId) ?? "未命名节点"}`
                  : "未提供节点路径"}
              </td>
              <td>{taxonomyLabel(edge.edgeType)}</td>
              <td>
                {edge.evidenceUseIds.length > 0
                  ? `证据使用 ${edge.evidenceUseIds.length}`
                  : "未提供"}
              </td>
              <td>
                <span>
                  {edge.relation
                    ? taxonomyLabel(edge.relation.relationType)
                    : edge.dataAggregation
                      ? `聚合行 ${edge.dataAggregation.projectedRowCount}`
                      : "未提供关系明细"}
                </span>
                {edge.relationTrace ? (
                  <small>
                    推导证据 {edge.relationTrace.traceEvidenceIds.length}
                  </small>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(edges.length, visible.length, "条边") ? (
        <p className="scientific-artifact__table-note">
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
      <ScientificContentHeader title={title} subtitle="证据图谱" />
      <div className="scientific-artifact__summary" aria-label="证据图谱摘要">
        <span>节点 {review.nodeCount}</span>
        <span>边 {review.edgeCount}</span>
        <span>证据使用 {review.evidenceUseCount}</span>
        <span>{sourceModeLabel(review.sourceMode)}</span>
      </div>
      {review.integrity.findings.length > 0 ? (
        <p className="scientific-artifact__warning">
          完整性发现：{review.integrity.findings[0]?.message ?? "未提供说明"}
        </p>
      ) : null}
      <section className="scientific-artifact__section">
        <h4>节点</h4>
        {review.nodes.length > 0 ? (
          <NodeTable nodes={review.nodes} surface={surface} />
        ) : (
          <p className="scientific-artifact__empty">
            当前版本没有可展示的节点。
          </p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>边</h4>
        {review.edges.length > 0 ? (
          <EdgeTable
            edges={review.edges}
            nodeLabelById={nodeLabelById}
            surface={surface}
          />
        ) : (
          <p className="scientific-artifact__empty">当前版本没有可展示的边。</p>
        )}
      </section>
    </article>
  );
}
