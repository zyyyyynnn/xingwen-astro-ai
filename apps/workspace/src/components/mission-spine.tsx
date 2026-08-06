import type { RunStatus } from "@xingwen/domain";

export interface MissionSpineProps {
  readonly currentPhase: number;
  readonly blockedPhases?: readonly number[];
  readonly onPhaseClick?: (phase: number) => void;
}

export const MISSION_PHASES = [
  "问题定义",
  "协议确认",
  "证据采集",
  "分析验证",
  "结论形成",
  "复核交付",
] as const;

/**
 * Map a RunStatus to a 0-based mission phase index.
 *
 * The mapping is intentionally conservative: terminal failure/cancellation
 * keeps the spine at the last attempted phase rather than advancing.
 */
export function phaseFromRunStatus(status: RunStatus | null): number {
  if (!status) return 0;
  switch (status) {
    case "queued":
    case "planning":
      return 0;
    case "fetching_data":
    case "cleaning_data":
      return 2;
    case "searching_papers":
    case "summarizing_papers":
    case "reasoning_literature":
    case "building_graph":
      return 3;
    case "waiting_for_input":
      return 4;
    case "completed":
      return 5;
    case "failed":
    case "cancelled":
      return 4;
    default:
      return 0;
  }
}

/** Six-phase compact progress spine. */
export function MissionSpine({
  currentPhase,
  blockedPhases = [],
  onPhaseClick,
}: MissionSpineProps) {
  const clamped = Math.max(
    0,
    Math.min(currentPhase, MISSION_PHASES.length - 1),
  );
  return (
    <ol className="mission-spine" aria-label="研究阶段进度">
      {MISSION_PHASES.map((label, index) => {
        const isComplete = index < clamped;
        const isCurrent = index === clamped;
        const isBlocked = blockedPhases.includes(index);
        const isClickable = Boolean(onPhaseClick) && !isBlocked;
        const stateClass = isComplete
          ? "mission-spine__phase--complete"
          : isCurrent
            ? "mission-spine__phase--current"
            : isBlocked
              ? "mission-spine__phase--blocked"
              : "";
        return (
          <li key={label} className={`mission-spine__phase ${stateClass}`}>
            <button
              type="button"
              className="mission-spine__phase-button"
              onClick={() => isClickable && onPhaseClick?.(index)}
              disabled={!isClickable}
              aria-current={isCurrent ? "step" : undefined}
            >
              <span className="mission-spine__phase-index">{index + 1}</span>
              <span className="mission-spine__phase-label">{label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
