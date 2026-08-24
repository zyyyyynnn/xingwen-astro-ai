import { graphlib, layout } from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import type { DomainEntityId, GraphEdgeReview } from "@xingwen/domain";
import { workspaceGraphGeometry } from "@xingwen/design-tokens";
import type { GraphArtifactReviewViewModel } from "@xingwen/research-adapter";
import {
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";
import { Quote, Target } from "@xingwen/ui/icons";
import { useMemo, useState } from "react";

import {
  comparabilityLabel,
  ScientificContentHeader,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";

import "@xyflow/react/dist/style.css";

const INITIAL_NODE_BUDGET = 60;
const NODE_BUDGET_INCREMENT = 60;

interface ScientificGraphNodeData extends Record<string, unknown> {
  readonly label: string;
  readonly typeLabel: string;
}

type ScientificGraphNode = Node<ScientificGraphNodeData, "scientific">;
type ScientificGraphEdge = Edge<{ readonly review: GraphEdgeReview }>;

function unique<T>(values: readonly T[]): T[] {
  return [...new Set(values)];
}

function evidenceIdsForEdge(edge: GraphEdgeReview): DomainEntityId[] {
  return unique([
    ...edge.evidenceIds,
    ...(edge.relation?.evidenceIds ?? []),
    ...(edge.relation?.reasoningTrace?.evidenceIds ?? []),
    ...(edge.relationTrace?.traceEvidenceIds ?? []),
  ]);
}

function isPresentableEdge(edge: GraphEdgeReview): boolean {
  if (evidenceIdsForEdge(edge).length === 0) return false;
  if (edge.relation === null && edge.relationTrace === null) return true;
  return (
    edge.relation?.status === "accepted" &&
    edge.relation.graphEligible &&
    edge.relation.reasoningTrace !== null &&
    edge.relationTrace?.relationStatus === "accepted"
  );
}

function ScientificNode({ data, selected }: NodeProps<ScientificGraphNode>) {
  return (
    <div
      className="graph-workspace__node"
      data-selected={selected || undefined}
    >
      <Handle type="target" position={Position.Left} />
      <span>{data.typeLabel}</span>
      <strong>{data.label}</strong>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { scientific: ScientificNode };

function layoutElements(
  nodes: readonly GraphArtifactReviewViewModel["nodes"][number][],
  edges: readonly GraphEdgeReview[],
): {
  readonly nodes: ScientificGraphNode[];
  readonly edges: ScientificGraphEdge[];
} {
  const graph = new graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    nodesep: workspaceGraphGeometry.nodeSeparation,
    ranksep: workspaceGraphGeometry.rankSeparation,
  });
  for (const node of nodes) {
    graph.setNode(node.nodeId, {
      width: workspaceGraphGeometry.nodeInlineSize,
      height: workspaceGraphGeometry.nodeBlockSize,
    });
  }
  for (const edge of edges) {
    if (edge.sourceNodeId && edge.targetNodeId) {
      graph.setEdge(edge.sourceNodeId, edge.targetNodeId);
    }
  }
  layout(graph);
  return {
    nodes: nodes.map((node) => {
      const position = graph.node(node.nodeId);
      return {
        id: node.nodeId,
        type: "scientific",
        position: {
          x: position.x - workspaceGraphGeometry.nodeInlineSize / 2,
          y: position.y - workspaceGraphGeometry.nodeBlockSize / 2,
        },
        data: {
          label: node.label || "未命名研究对象",
          typeLabel: taxonomyLabel(node.nodeType),
        },
        ariaLabel: `${taxonomyLabel(node.nodeType)}：${node.label || "未命名研究对象"}`,
        draggable: false,
        selectable: true,
      };
    }),
    edges: edges.flatMap((edge) => {
      if (!edge.sourceNodeId || !edge.targetNodeId) return [];
      return [
        {
          id: edge.edgeId,
          source: edge.sourceNodeId,
          target: edge.targetNodeId,
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed },
          data: { review: edge },
          ariaLabel: taxonomyLabel(edge.edgeType),
          className: "graph-workspace__edge",
          focusable: true,
          selectable: true,
        },
      ];
    }),
  };
}

function GraphFilters({
  query,
  onQueryChange,
  nodeType,
  onNodeTypeChange,
  edgeType,
  onEdgeTypeChange,
  nodeTypes: availableNodeTypes,
  edgeTypes: availableEdgeTypes,
}: {
  readonly query: string;
  readonly onQueryChange: (value: string) => void;
  readonly nodeType: string;
  readonly onNodeTypeChange: (value: string) => void;
  readonly edgeType: string;
  readonly onEdgeTypeChange: (value: string) => void;
  readonly nodeTypes: readonly string[];
  readonly edgeTypes: readonly string[];
}) {
  return (
    <div className="graph-workspace__filters" aria-label="关系图筛选">
      <Input
        type="search"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="筛选研究对象"
        aria-label="按名称筛选研究对象"
      />
      <Select value={nodeType} onValueChange={onNodeTypeChange}>
        <SelectTrigger aria-label="筛选节点类别">
          <SelectValue placeholder="全部对象类别" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部对象类别</SelectItem>
          {availableNodeTypes.map((value) => (
            <SelectItem key={value} value={value}>
              {taxonomyLabel(value)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={edgeType} onValueChange={onEdgeTypeChange}>
        <SelectTrigger aria-label="筛选关系类别">
          <SelectValue placeholder="全部关系类别" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部关系类别</SelectItem>
          {availableEdgeTypes.map((value) => (
            <SelectItem key={value} value={value}>
              {taxonomyLabel(value)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function EdgeDetails({
  edge,
  nodeLabelById,
  onSelectEvidence,
}: {
  readonly edge: GraphEdgeReview;
  readonly nodeLabelById: ReadonlyMap<DomainEntityId, string>;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const evidenceIds = evidenceIdsForEdge(edge);
  const relation = edge.relation;
  const trace = relation?.reasoningTrace ?? null;
  return (
    <aside className="graph-workspace__selection" aria-live="polite">
      <header>
        <p>{taxonomyLabel(edge.edgeType)}</p>
        <h4>
          {edge.sourceNodeId
            ? (nodeLabelById.get(edge.sourceNodeId) ?? "未命名研究对象")
            : "起点未公开"}
          <span aria-hidden="true">→</span>
          {edge.targetNodeId
            ? (nodeLabelById.get(edge.targetNodeId) ?? "未命名研究对象")
            : "终点未公开"}
        </h4>
      </header>
      {relation ? (
        <dl>
          <div>
            <dt>关系</dt>
            <dd>{taxonomyLabel(relation.relationType)}</dd>
          </div>
          <div>
            <dt>可比性</dt>
            <dd>
              研究对象{comparabilityLabel(relation.comparability.objectStatus)}
              ， 指标{comparabilityLabel(relation.comparability.metricStatus)}
              ，单位
              {comparabilityLabel(relation.comparability.unitStatus)}
            </dd>
          </div>
          {relation.conditions.length > 0 ? (
            <div>
              <dt>成立条件</dt>
              <dd>{relation.conditions.join("；")}</dd>
            </div>
          ) : null}
          {trace ? (
            <div>
              <dt>公开推导</dt>
              <dd>
                <p>{trace.conclusion}</p>
                {trace.steps.length > 0 ? (
                  <ol>
                    {trace.steps.map((step) => (
                      <li key={step.order}>{step.statement}</li>
                    ))}
                  </ol>
                ) : null}
              </dd>
            </div>
          ) : null}
          {trace &&
          (trace.conflicts.length > 0 || trace.limitations.length > 0) ? (
            <div>
              <dt>冲突与限制</dt>
              <dd>{[...trace.conflicts, ...trace.limitations].join("；")}</dd>
            </div>
          ) : null}
        </dl>
      ) : edge.dataAggregation ? (
        <p>
          该关系汇总了 {edge.dataAggregation.projectedRowCount}{" "}
          条可核验记录；其中
          {edge.dataAggregation.conflictCount} 条存在冲突。
        </p>
      ) : (
        <p>这条关系没有更多可公开说明。</p>
      )}
      <div className="graph-workspace__evidence-actions">
        {evidenceIds.length > 0 && onSelectEvidence ? (
          evidenceIds.map((evidenceId, index) => (
            <Button
              key={evidenceId}
              size="small"
              variant="ghost"
              onClick={() => onSelectEvidence(evidenceId)}
            >
              <Quote aria-hidden="true" />
              查看证据 {index + 1}
            </Button>
          ))
        ) : (
          <p>没有可公开核验的证据。</p>
        )}
      </div>
    </aside>
  );
}

function GraphList({
  edges,
  nodeLabelById,
  selectedEdgeId,
  onSelectEdge,
}: {
  readonly edges: readonly GraphEdgeReview[];
  readonly nodeLabelById: ReadonlyMap<DomainEntityId, string>;
  readonly selectedEdgeId: DomainEntityId | null;
  readonly onSelectEdge: (edgeId: DomainEntityId) => void;
}) {
  if (edges.length === 0) {
    return <p className="graph-workspace__empty">当前筛选下没有可核验关系。</p>;
  }
  return (
    <ol className="graph-workspace__list" aria-label="关系图列表替代视图">
      {edges.map((edge) => (
        <li key={edge.edgeId}>
          <Button
            variant={selectedEdgeId === edge.edgeId ? "secondary" : "ghost"}
            onClick={() => onSelectEdge(edge.edgeId)}
          >
            <span>
              {edge.sourceNodeId
                ? (nodeLabelById.get(edge.sourceNodeId) ?? "未命名研究对象")
                : "起点未公开"}
            </span>
            <span aria-hidden="true">→</span>
            <span>
              {edge.targetNodeId
                ? (nodeLabelById.get(edge.targetNodeId) ?? "未命名研究对象")
                : "终点未公开"}
            </span>
            <small>{taxonomyLabel(edge.edgeType)}</small>
          </Button>
        </li>
      ))}
    </ol>
  );
}

export function GraphContent({
  review,
  title,
  surface,
  onSelectEvidence,
}: {
  readonly review: GraphArtifactReviewViewModel;
  readonly title: string;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const [query, setQuery] = useState("");
  const [nodeType, setNodeType] = useState("all");
  const [edgeType, setEdgeType] = useState("all");
  const [nodeBudget, setNodeBudget] = useState(INITIAL_NODE_BUDGET);
  const [selectedNodeId, setSelectedNodeId] = useState<DomainEntityId | null>(
    null,
  );
  const [selectedEdgeId, setSelectedEdgeId] = useState<DomainEntityId | null>(
    null,
  );
  const [instance, setInstance] = useState<
    ReactFlowInstance<ScientificGraphNode, ScientificGraphEdge> | undefined
  >();

  const nodeLabelById = useMemo(
    () =>
      new Map<DomainEntityId, string>(
        review.nodes.map((node) => [
          node.nodeId,
          node.label || "未命名研究对象",
        ]),
      ),
    [review.nodes],
  );
  const presentableEdges = useMemo(
    () => review.edges.filter(isPresentableEdge),
    [review.edges],
  );
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matchingNodes = useMemo(
    () =>
      review.nodes.filter(
        (node) =>
          (nodeType === "all" || node.nodeType === nodeType) &&
          (normalizedQuery === "" ||
            node.label.toLocaleLowerCase().includes(normalizedQuery)),
      ),
    [nodeType, normalizedQuery, review.nodes],
  );
  const visibleNodes = matchingNodes.slice(0, nodeBudget);
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.nodeId));
  const visibleEdges = presentableEdges.filter(
    (edge) =>
      (edgeType === "all" || edge.edgeType === edgeType) &&
      edge.sourceNodeId !== null &&
      edge.targetNodeId !== null &&
      visibleNodeIds.has(edge.sourceNodeId) &&
      visibleNodeIds.has(edge.targetNodeId),
  );
  const elements = useMemo(
    () => layoutElements(visibleNodes, visibleEdges),
    [visibleEdges, visibleNodes],
  );
  const selectedEdge =
    presentableEdges.find((edge) => edge.edgeId === selectedEdgeId) ?? null;
  const selectedNode =
    review.nodes.find((node) => node.nodeId === selectedNodeId) ?? null;
  const hiddenUnsafeEdgeCount = review.edges.length - presentableEdges.length;

  const focusSelection = () => {
    const id = selectedEdgeId ?? selectedNodeId;
    if (!instance || !id) return;
    const nodes = selectedEdge
      ? [selectedEdge.sourceNodeId, selectedEdge.targetNodeId]
          .filter((value): value is DomainEntityId => value !== null)
          .map((nodeId) => ({ id: nodeId }))
      : [{ id }];
    void instance.fitView({
      nodes,
      padding: workspaceGraphGeometry.focusPadding,
    });
  };

  return (
    <article
      className="scientific-artifact scientific-artifact--graph"
      data-surface={surface}
    >
      <ScientificContentHeader
        title={title}
        subtitle={`可核验证据关系，${presentableEdges.length} 条`}
      />
      {hiddenUnsafeEdgeCount > 0 ? (
        <p className="graph-workspace__notice">
          有 {hiddenUnsafeEdgeCount} 条关系因证据或公开推导不完整而未显示。
        </p>
      ) : null}
      <GraphFilters
        query={query}
        onQueryChange={setQuery}
        nodeType={nodeType}
        onNodeTypeChange={setNodeType}
        edgeType={edgeType}
        onEdgeTypeChange={setEdgeType}
        nodeTypes={unique(review.nodes.map((node) => node.nodeType)).sort()}
        edgeTypes={unique(presentableEdges.map((edge) => edge.edgeType)).sort()}
      />
      <Tabs defaultValue="canvas" className="graph-workspace">
        <div className="graph-workspace__toolbar">
          <TabsList aria-label="关系图展示方式">
            <TabsTrigger value="canvas">关系图</TabsTrigger>
            <TabsTrigger value="list">列表</TabsTrigger>
          </TabsList>
          {selectedEdgeId || selectedNodeId ? (
            <Button size="small" variant="ghost" onClick={focusSelection}>
              <Target aria-hidden="true" />
              聚焦选择
            </Button>
          ) : null}
        </div>
        <TabsContent value="canvas" className="graph-workspace__canvas-panel">
          {elements.nodes.length > 0 ? (
            <ReactFlow<ScientificGraphNode, ScientificGraphEdge>
              nodes={elements.nodes.map((node) => ({
                ...node,
                selected: node.id === selectedNodeId,
              }))}
              edges={elements.edges.map((edge) => ({
                ...edge,
                selected: edge.id === selectedEdgeId,
              }))}
              nodeTypes={nodeTypes}
              onInit={setInstance}
              onNodeClick={(_event, node) => {
                setSelectedNodeId(node.id as DomainEntityId);
                setSelectedEdgeId(null);
              }}
              onEdgeClick={(_event, edge) => {
                setSelectedEdgeId(edge.id as DomainEntityId);
                setSelectedNodeId(null);
              }}
              onPaneClick={() => {
                setSelectedNodeId(null);
                setSelectedEdgeId(null);
              }}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              nodesFocusable
              edgesFocusable
              disableKeyboardA11y={false}
              deleteKeyCode={null}
              fitView
              aria-label="可交互科学关系图"
              ariaLabelConfig={{
                "node.a11yDescription.default":
                  "按回车或空格选择研究对象，按 Escape 取消选择。",
                "edge.a11yDescription.default":
                  "按回车或空格选择关系，按 Escape 取消选择。",
                "controls.ariaLabel": "关系图视图控制",
              }}
            >
              <Background />
              <Controls showInteractive={false} />
            </ReactFlow>
          ) : (
            <p className="graph-workspace__empty">
              当前筛选下没有可展示的研究对象。
            </p>
          )}
        </TabsContent>
        <TabsContent value="list">
          <GraphList
            edges={visibleEdges}
            nodeLabelById={nodeLabelById}
            selectedEdgeId={selectedEdgeId}
            onSelectEdge={(id) => {
              setSelectedEdgeId(id);
              setSelectedNodeId(null);
            }}
          />
        </TabsContent>
      </Tabs>
      {matchingNodes.length > visibleNodes.length ? (
        <Button
          variant="secondary"
          onClick={() =>
            setNodeBudget((current) => current + NODE_BUDGET_INCREMENT)
          }
          className="graph-workspace__load-more"
        >
          显示更多研究对象
        </Button>
      ) : null}
      {selectedEdge ? (
        <EdgeDetails
          edge={selectedEdge}
          nodeLabelById={nodeLabelById}
          onSelectEvidence={onSelectEvidence}
        />
      ) : selectedNode ? (
        <aside className="graph-workspace__selection" aria-live="polite">
          <header>
            <p>{taxonomyLabel(selectedNode.nodeType)}</p>
            <h4>{selectedNode.label || "未命名研究对象"}</h4>
          </header>
          <p>选择与此对象连接的关系，可继续查看公开推导与来源证据。</p>
        </aside>
      ) : null}
    </article>
  );
}
