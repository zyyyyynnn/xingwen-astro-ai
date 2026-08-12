import type {
  ActivityPresentationEvent,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";
import { Alert, AlertDescription } from "@xingwen/ui";
import { History, ListChecks } from "@xingwen/ui/icons";
import { useEffect, useRef, useState } from "react";

import {
  Messages,
  NarrativeDisclosure,
} from "../../upstream/openhands/src/root";
import {
  ResearchPlanStatusIcon,
  researchPlanStatusLabel,
  researchPlanSummary,
} from "./research-plan";
import type { ResearchPlanItem } from "../presentation/research-presentation";

interface ResearchProcessProjectionProps {
  readonly visible: boolean;
  readonly run: ResearchRunViewModel | null;
  readonly planItems: readonly ResearchPlanItem[];
  readonly events: readonly ActivityPresentationEvent[];
  readonly eventError: string | null;
  readonly focusPlanRequest: number;
}

export function ResearchProcessProjection({
  visible,
  run,
  planItems,
  events,
  eventError,
  focusPlanRequest,
}: ResearchProcessProjectionProps) {
  const planState = researchPlanSummary(planItems);
  const latestEvent = events.at(-1);
  const planTriggerRef = useRef<HTMLButtonElement>(null);
  const [planOpen, setPlanOpen] = useState(
    planState === "等待你的回答" || planState === "需要处理",
  );

  useEffect(() => {
    if (!visible || focusPlanRequest === 0) return;
    let scrollFrame = 0;
    const frame = requestAnimationFrame(() => {
      setPlanOpen(true);
      scrollFrame = requestAnimationFrame(() => {
        planTriggerRef.current?.scrollIntoView({ block: "center" });
      });
    });
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(scrollFrame);
    };
  }, [focusPlanRequest, visible]);

  if (!visible) return null;
  return (
    <section className="research-process" aria-label="研究过程">
      <NarrativeDisclosure
        summary="研究计划"
        meta={planState}
        icon={ListChecks}
        open={planOpen}
        onOpenChange={setPlanOpen}
        triggerRef={planTriggerRef}
      >
        <ol className="research-plan">
          {planItems.map((item) => (
            <li key={item.id} data-status={item.status}>
              <span className="research-plan__icon">
                <ResearchPlanStatusIcon status={item.status} />
              </span>
              <span className="research-plan__content">
                <span className="research-plan__label">{item.label}</span>
                {item.detail ? (
                  <span className="research-plan__detail">{item.detail}</span>
                ) : null}
              </span>
              <span className="research-plan__state">
                {researchPlanStatusLabel(item.status)}
              </span>
            </li>
          ))}
        </ol>
      </NarrativeDisclosure>
      {run ? (
        <NarrativeDisclosure
          summary="运行记录"
          meta={latestEvent?.title ?? "正在同步"}
          icon={History}
        >
          {events.length > 0 ? (
            <Messages events={events} />
          ) : (
            <p className="research-process__empty">正在同步运行记录…</p>
          )}
          {eventError ? (
            <Alert variant="destructive">
              <AlertDescription>{eventError}</AlertDescription>
            </Alert>
          ) : null}
        </NarrativeDisclosure>
      ) : null}
    </section>
  );
}
