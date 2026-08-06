import type { ReactNode } from "react";

export type ContextRailScene =
  "brief" | "active" | "artifact_review" | "source_review" | "completion";

export interface ContextHistoryEntry {
  readonly id: string;
  readonly label: string;
  readonly kind: string;
}

export interface ResearchContextRailProps {
  readonly mode: "hidden" | "summary" | "detail";
  readonly scene: ContextRailScene;
  readonly evidenceSummary?: {
    readonly supported: number;
    readonly conflicted: number;
    readonly unresolved: number;
    readonly total: number;
  };
  readonly pendingReviewCount?: number;
  readonly currentArtifact?: {
    readonly title: string;
    readonly kind: string;
    readonly version: number;
    readonly status: string;
  } | null;
  readonly missionContext?: {
    readonly researchGoal: string;
    readonly requestedFields: readonly string[];
  } | null;
  readonly contextHistory?: readonly ContextHistoryEntry[];
  readonly railWidth?: number;
  readonly onModeChange?: (mode: "hidden" | "summary" | "detail") => void;
  readonly onCardClick?: (cardType: string) => void;
  readonly onHistoryClick?: (entry: ContextHistoryEntry) => void;
  readonly onClearHistory?: () => void;
  readonly onRailWidthChange?: (width: number) => void;
}

interface SceneCardConfig {
  readonly cardType: string;
  readonly title: string;
  readonly render: (props: ResearchContextRailProps) => ReactNode;
}

const SCENE_CARDS: readonly SceneCardConfig[] = [
  {
    cardType: "mission_context",
    title: "研究使命",
    render: ({ missionContext }) => (
      <>
        <p className="research-context-rail__card-value">
          {missionContext?.researchGoal ?? "尚无研究目标"}
        </p>
        {missionContext && missionContext.requestedFields.length > 0 ? (
          <p className="research-context-rail__card-meta">
            字段：{missionContext.requestedFields.join("、")}
          </p>
        ) : null}
      </>
    ),
  },
  {
    cardType: "evidence",
    title: "证据覆盖",
    render: ({ evidenceSummary }) =>
      evidenceSummary ? (
        <dl className="research-context-rail__stats">
          <div>
            <dt>覆盖</dt>
            <dd>{evidenceSummary.total}</dd>
          </div>
          <div>
            <dt>支持</dt>
            <dd>{evidenceSummary.supported}</dd>
          </div>
          <div>
            <dt>冲突</dt>
            <dd>{evidenceSummary.conflicted}</dd>
          </div>
          <div>
            <dt>未决</dt>
            <dd>{evidenceSummary.unresolved}</dd>
          </div>
        </dl>
      ) : (
        <p className="research-context-rail__card-meta">尚无证据数据</p>
      ),
  },
  {
    cardType: "pending_review",
    title: "待复核",
    render: ({ pendingReviewCount }) => (
      <p className="research-context-rail__card-value">
        {pendingReviewCount ?? 0} 项待复核
      </p>
    ),
  },
  {
    cardType: "artifact",
    title: "当前产物",
    render: ({ currentArtifact }) =>
      currentArtifact ? (
        <>
          <p className="research-context-rail__card-value">
            {currentArtifact.title}
          </p>
          <p className="research-context-rail__card-meta">
            {currentArtifact.kind} · v{currentArtifact.version} ·{" "}
            {currentArtifact.status}
          </p>
        </>
      ) : (
        <p className="research-context-rail__card-meta">未选择产物</p>
      ),
  },
];

const SCENE_CARD_MAP: Record<ContextRailScene, readonly string[]> = {
  brief: ["mission_context", "evidence"],
  active: ["evidence", "pending_review", "artifact"],
  artifact_review: ["artifact", "evidence"],
  source_review: ["evidence", "pending_review"],
  completion: ["mission_context", "evidence", "artifact"],
};

const DETAIL_PANELS: Record<ContextRailScene, string> = {
  brief: "mission_context",
  active: "evidence",
  artifact_review: "artifact",
  source_review: "evidence",
  completion: "mission_context",
};

function renderDetailPanel(props: ResearchContextRailProps): ReactNode {
  const panelType = DETAIL_PANELS[props.scene];
  const config = SCENE_CARDS.find((c) => c.cardType === panelType);
  if (!config) return null;
  return (
    <section
      className="research-context-rail__detail"
      aria-label={config.title}
    >
      <p className="research-context-rail__detail-title">{config.title}</p>
      <div className="research-context-rail__detail-body">
        {config.render(props)}
      </div>
    </section>
  );
}

/** Right sidebar: scene-aware context cards, detail panel, history and resize. */
export function ResearchContextRail({
  mode,
  scene,
  evidenceSummary,
  pendingReviewCount,
  currentArtifact,
  missionContext,
  contextHistory = [],
  railWidth,
  onModeChange,
  onCardClick,
  onHistoryClick,
  onClearHistory,
  onRailWidthChange,
}: ResearchContextRailProps) {
  if (mode === "hidden") {
    return (
      <div className="research-context-rail research-context-rail--hidden">
        <button
          type="button"
          className="research-context-rail__expand"
          onClick={() => onModeChange?.("summary")}
          aria-label="展开上下文栏"
        >
          展开上下文
        </button>
      </div>
    );
  }

  const showDetail = mode === "detail";
  const visibleCardTypes = SCENE_CARD_MAP[scene] ?? SCENE_CARD_MAP.active;
  const visibleCards = visibleCardTypes
    .map((type) => SCENE_CARDS.find((c) => c.cardType === type))
    .filter((c): c is SceneCardConfig => c !== undefined);

  const handleResizeStart = (event: React.MouseEvent) => {
    if (!onRailWidthChange) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidth ?? 224;
    const handleMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const next = Math.max(180, Math.min(384, startWidth + delta));
      onRailWidthChange(next);
    };
    const handleUp = () => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
    };
    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);
  };

  return (
    <div className="research-context-rail">
      {onRailWidthChange ? (
        <div
          className="research-context-rail__resize-handle"
          onMouseDown={handleResizeStart}
          role="separator"
          aria-orientation="vertical"
          aria-label="调整上下文栏宽度"
        />
      ) : null}
      <div className="research-context-rail__header">
        <span className="region-label">上下文</span>
        <button
          type="button"
          className="research-context-rail__toggle"
          onClick={() => onModeChange?.(showDetail ? "summary" : "detail")}
        >
          {showDetail ? "收起详情" : "展开详情"}
        </button>
        <button
          type="button"
          className="research-context-rail__hide"
          onClick={() => onModeChange?.("hidden")}
          aria-label="隐藏上下文栏"
        >
          隐藏
        </button>
      </div>

      {showDetail ? (
        renderDetailPanel({
          scene,
          evidenceSummary,
          pendingReviewCount,
          currentArtifact,
          missionContext,
          mode,
          onCardClick,
        })
      ) : (
        <div className="research-context-rail__cards">
          {visibleCards.map((card) => (
            <button
              key={card.cardType}
              type="button"
              className="research-context-rail__card"
              onClick={() => onCardClick?.(card.cardType)}
            >
              <p className="research-context-rail__card-title">{card.title}</p>
              {card.render({
                scene,
                evidenceSummary,
                pendingReviewCount,
                currentArtifact,
                missionContext,
                mode,
                onCardClick,
              })}
            </button>
          ))}
        </div>
      )}

      {contextHistory.length > 0 ? (
        <section
          className="research-context-rail__history"
          aria-label="上下文历史"
        >
          <div className="research-context-rail__history-header">
            <span className="region-label">历史</span>
            {onClearHistory ? (
              <button
                type="button"
                className="research-context-rail__history-clear"
                onClick={onClearHistory}
              >
                清除
              </button>
            ) : null}
          </div>
          <ol className="research-context-rail__history-list">
            {contextHistory.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  className="research-context-rail__history-item"
                  onClick={() => onHistoryClick?.(entry)}
                >
                  <span className="research-context-rail__history-kind">
                    {entry.kind}
                  </span>
                  <span className="research-context-rail__history-label">
                    {entry.label}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
