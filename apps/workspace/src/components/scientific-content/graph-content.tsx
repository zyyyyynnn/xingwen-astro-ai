import { graphlib, layout } from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import type {
  DomainEntityId,
  GraphEdgeReview,
  PublicArtifactPresentation,
} from "@xingwen/domain";
import { workspaceGraphGeometry } from "@xingwen/design-tokens";
import type { GraphArtifactReviewViewModel } from "@xingwen/research-adapter";
import {
  Badge,
  Button,
  Input,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";
import { Quote, Target } from "@xingwen/ui/icons";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  comparabilityLabel,
  ScientificContentHeader,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";
import { PresentationGraphRelationships } from "../scientific-presentation";

import "@xyflow/react/dist/style.css";

const INITIAL_NODE_BUDGET = 60;
const NODE_BUDGET_INCREMENT = 60;
const OVERVIEW_FIT_OPTIONS = { padding: 0.08, maxZoom: 1.25 };

function GraphCanvasFit() {
  const { fitView } = useReactFlow();
  const width = useStore((state) => state.width);
  const height = useStore((state) => state.height);
  useEffect(() => {
    if (width > 0 && height > 0) void fitView(OVERVIEW_FIT_OPTIONS);
  }, [fitView, height, width]);
  return null;
}

interface ResolvedGraphGeometry {
  readonly nodeInlineSize: number;
  readonly nodeBlockSize: number;
  readonly nodeSeparation: number;
  readonly rankSeparation: number;
  readonly focusPadding: number;
}

function readCssNumber(variable: string, length: boolean): number | null {
  const root = document.documentElement;
  const value = getComputedStyle(root).getPropertyValue(variable).trim();
  if (!value) return null;
  if (!length) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  const match = value.match(/^([\d.]+)(px|rem)$/u);
  if (!match) return null;
  const number = Number(match[1]);
  if (!Number.isFinite(number)) return null;
  if (match[2] === "px") return number;
  const rootFontSize = Number.parseFloat(getComputedStyle(root).fontSize);
  return Number.isFinite(rootFontSize) ? number * rootFontSize : null;
}

function readGraphGeometry(
  probe: HTMLElement | null,
): ResolvedGraphGeometry | null {
  const bounds = probe?.getBoundingClientRect();
  const nodeInlineSize =
    bounds && bounds.width > 0
      ? bounds.width
      : readCssNumber(workspaceGraphGeometry.nodeInlineSize, true);
  const nodeBlockSize =
    bounds && bounds.height > 0
      ? bounds.height
      : readCssNumber(workspaceGraphGeometry.nodeBlockSize, true);
  const nodeSeparation = readCssNumber(
    workspaceGraphGeometry.nodeSeparation,
    true,
  );
  const rankSeparation = readCssNumber(
    workspaceGraphGeometry.rankSeparation,
    true,
  );
  const focusPadding = readCssNumber(
    workspaceGraphGeometry.focusPadding,
    false,
  );
  return nodeInlineSize !== null &&
    nodeBlockSize !== null &&
    nodeSeparation !== null &&
    rankSeparation !== null &&
    focusPadding !== null
    ? {
        nodeInlineSize,
        nodeBlockSize,
        nodeSeparation,
        rankSeparation,
        focusPadding,
      }
    : null;
}

function useGraphGeometry() {
  const probeRef = useRef<HTMLSpanElement>(null);
  const [geometry, setGeometry] = useState<ResolvedGraphGeometry | null>(null);
  useLayoutEffect(() => {
    const update = () => setGeometry(readGraphGeometry(probeRef.current));
    update();
    window.addEventListener("resize", update);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    if (probeRef.current) observer?.observe(probeRef.current);
    return () => {
      window.removeEventListener("resize", update);
      observer?.disconnect();
    };
  }, []);
  return { geometry, probeRef };
}

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
  return unique(edge.evidenceIds);
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
      <strong title={data.label}>{data.label}</strong>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { scientific: ScientificNode };

function layoutElements(
  nodes: readonly GraphArtifactReviewViewModel["nodes"][number][],
  edges: readonly GraphEdgeReview[],
  geometry: ResolvedGraphGeometry,
): {
  readonly nodes: ScientificGraphNode[];
  readonly edges: ScientificGraphEdge[];
} {
  const graph = new graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    nodesep: geometry.nodeSeparation,
    edgesep: geometry.nodeSeparation,
    ranksep: geometry.rankSeparation,
  });
  for (const node of nodes) {
    graph.setNode(node.nodeId, {
      width: geometry.nodeInlineSize,
      height: geometry.nodeBlockSize,
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
          x: position.x - geometry.nodeInlineSize / 2,
          y: position.y - geometry.nodeBlockSize / 2,
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
          <SelectGroup>
            <SelectItem value="all">全部对象类别</SelectItem>
            {availableNodeTypes.map((value) => (
              <SelectItem key={value} value={value}>
                {taxonomyLabel(value)}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select value={edgeType} onValueChange={onEdgeTypeChange}>
        <SelectTrigger aria-label="筛选关系类别">
          <SelectValue placeholder="全部关系类别" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="all">全部关系类别</SelectItem>
            {availableEdgeTypes.map((value) => (
              <SelectItem key={value} value={value}>
                {taxonomyLabel(value)}
              </SelectItem>
            ))}
          </SelectGroup>
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
          {relation.adjudication ? (
            <div>
              <dt>人工审定</dt>
              <dd>
                {relation.adjudication.decision === "accepted"
                  ? "已接受"
                  : "已拒绝"}
                ：{relation.adjudication.basis.join("；")}
              </dd>
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

export function GraphContent({
  review,
  presentation,
  surface,
  onSelectEvidence,
}: {
  readonly review: GraphArtifactReviewViewModel;
  readonly presentation: PublicArtifactPresentation;
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
  const { geometry: graphGeometry, probeRef } = useGraphGeometry();

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
    () =>
      graphGeometry
        ? layoutElements(visibleNodes, visibleEdges, graphGeometry)
        : { nodes: [], edges: [] },
    [graphGeometry, visibleEdges, visibleNodes],
  );
  const selectedEdge =
    presentableEdges.find((edge) => edge.edgeId === selectedEdgeId) ?? null;
  const selectedNode =
    review.nodes.find((node) => node.nodeId === selectedNodeId) ?? null;
  const selectedNodeConnectionCount = selectedNode
    ? presentableEdges.filter(
        (edge) =>
          edge.sourceNodeId === selectedNode.nodeId ||
          edge.targetNodeId === selectedNode.nodeId,
      ).length
    : 0;
  const hasSelection = selectedEdge !== null || selectedNode !== null;
  const hiddenUnsafeEdgeCount = review.edges.length - presentableEdges.length;
  const visibleNodeKeys = new Set(
    visibleNodes.map((node) => String(node.nodeId)),
  );
  const visibleEdgeKeys = new Set(
    visibleEdges.map((edge) => String(edge.edgeId)),
  );
  const presentationNodes = presentation.graphNodes.filter((node) =>
    visibleNodeKeys.has(node.key),
  );
  const presentationEdges = presentation.graphEdges.filter((edge) =>
    visibleEdgeKeys.has(edge.key),
  );

  const selectedCanvasNodes = useMemo(
    () =>
      selectedEdge
        ? [selectedEdge.sourceNodeId, selectedEdge.targetNodeId]
            .filter((value): value is DomainEntityId => value !== null)
            .map((id) => ({ id }))
        : selectedNode
          ? [{ id: selectedNode.nodeId }]
          : [],
    [selectedEdge, selectedNode],
  );

  const focusSelection = () => {
    if (!instance || selectedCanvasNodes.length === 0) return;
    void instance.fitView({
      nodes: selectedCanvasNodes,
      padding: graphGeometry?.focusPadding ?? 0,
    });
  };

  return (
    <article
      className="scientific-artifact scientific-artifact--graph"
      data-surface={surface}
    >
      <span
        ref={probeRef}
        className="graph-workspace__geometry-probe"
        aria-hidden="true"
      />
      <ScientificContentHeader
        title="证据关系网络"
        subtitle="选择研究对象或关系，核验公开推导与来源证据。"
      />
      <div className="graph-workspace__summary" aria-label="图谱摘要">
        <span>{review.nodes.length} 个研究对象</span>
        <span>{presentableEdges.length} 条公开关系</span>
        <span>
          {review.integrity.findings.length === 0
            ? "完整性校验通过"
            : `${review.integrity.findings.length} 项完整性提示`}
        </span>
        {hiddenUnsafeEdgeCount > 0 ? (
          <span className="graph-workspace__notice">
            {hiddenUnsafeEdgeCount} 条关系因证据或公开推导不完整而隐藏
          </span>
        ) : null}
      </div>
      <Tabs defaultValue="canvas" className="graph-workspace">
        <div className="graph-workspace__toolbar">
          <TabsList aria-label="关系图展示方式">
            <TabsTrigger value="canvas">关系图</TabsTrigger>
            <TabsTrigger value="list">列表</TabsTrigger>
          </TabsList>
          <GraphFilters
            query={query}
            onQueryChange={setQuery}
            nodeType={nodeType}
            onNodeTypeChange={setNodeType}
            edgeType={edgeType}
            onEdgeTypeChange={setEdgeType}
            nodeTypes={unique(review.nodes.map((node) => node.nodeType)).sort()}
            edgeTypes={unique(
              presentableEdges.map((edge) => edge.edgeType),
            ).sort()}
          />
          {hasSelection ? (
            <Button size="small" variant="secondary" onClick={focusSelection}>
              <Target data-icon="inline-start" aria-hidden="true" />
              聚焦选择
            </Button>
          ) : null}
        </div>
        <TabsContent value="canvas" className="graph-workspace__canvas-panel">
          <div
            className="graph-workspace__canvas-inspector-split"
            data-has-selection={hasSelection || undefined}
          >
            <div className="graph-workspace__canvas-holder">
              {graphGeometry === null ? (
                <p className="graph-workspace__empty" aria-busy="true">
                  正在适配关系图布局…
                </p>
              ) : elements.nodes.length > 0 ? (
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
                  onNodesChange={(changes) => {
                    const selection = changes.find(
                      (change) => change.type === "select" && change.selected,
                    );
                    if (selection?.type === "select") {
                      setSelectedNodeId(selection.id as DomainEntityId);
                      setSelectedEdgeId(null);
                    } else if (
                      changes.some(
                        (change) =>
                          change.type === "select" &&
                          change.id === selectedNodeId &&
                          !change.selected,
                      )
                    ) {
                      setSelectedNodeId(null);
                    }
                  }}
                  onEdgesChange={(changes) => {
                    const selection = changes.find(
                      (change) => change.type === "select" && change.selected,
                    );
                    if (selection?.type === "select") {
                      setSelectedEdgeId(selection.id as DomainEntityId);
                      setSelectedNodeId(null);
                    } else if (
                      changes.some(
                        (change) =>
                          change.type === "select" &&
                          change.id === selectedEdgeId &&
                          !change.selected,
                      )
                    ) {
                      setSelectedEdgeId(null);
                    }
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
                  fitViewOptions={OVERVIEW_FIT_OPTIONS}
                  aria-label="可交互科学关系图"
                  ariaLabelConfig={{
                    "node.a11yDescription.default":
                      "按回车或空格选择研究对象，按 Escape 取消选择。",
                    "edge.a11yDescription.default":
                      "按回车或空格选择关系，按 Escape 取消选择。",
                    "controls.ariaLabel": "关系图视图控制",
                  }}
                >
                  <GraphCanvasFit />
                  <Background />
                  <Controls showInteractive={false} />
                </ReactFlow>
              ) : (
                <p className="graph-workspace__empty">
                  当前筛选下没有可展示的研究对象。
                </p>
              )}
            </div>
            {hasSelection ? (
              <div className="graph-workspace__side-inspector">
                {selectedEdge ? (
                  <EdgeDetails
                    edge={selectedEdge}
                    nodeLabelById={nodeLabelById}
                    onSelectEvidence={onSelectEvidence}
                  />
                ) : selectedNode ? (
                  <aside
                    className="graph-workspace__selection"
                    aria-live="polite"
                  >
                    <header>
                      <Badge variant="secondary">
                        {taxonomyLabel(selectedNode.nodeType)}
                      </Badge>
                      <h4>{selectedNode.label || "未命名研究对象"}</h4>
                    </header>
                    <dl>
                      <div>
                        <dt>可核验关系</dt>
                        <dd>{selectedNodeConnectionCount} 条</dd>
                      </div>
                      <div>
                        <dt>冻结结果版本</dt>
                        <dd>{selectedNode.versionBindings.length} 个</dd>
                      </div>
                    </dl>
                    <p>
                      选择与此对象连接的关系，可继续查看公开推导与来源证据。
                    </p>
                  </aside>
                ) : null}
              </div>
            ) : null}
          </div>
        </TabsContent>
        <TabsContent value="list">
          {presentationEdges.length > 0 ? (
            <PresentationGraphRelationships
              nodes={presentationNodes}
              edges={presentationEdges}
              selectedKey={selectedEdgeId}
              onSelectRelationship={(id) => {
                setSelectedEdgeId(id as DomainEntityId);
                setSelectedNodeId(null);
              }}
            />
          ) : (
            <p className="graph-workspace__empty">当前筛选下没有可核验关系。</p>
          )}
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
    </article>
  );
}
