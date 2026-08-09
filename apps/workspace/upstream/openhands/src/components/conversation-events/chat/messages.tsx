import React from "react";

import { CollapsibleRationale } from "./event-message-components/collapsible-thinking";
import { EventGroup } from "./event-message-components/event-group";
import { EventMessage } from "./event-message";
import { groupEvents, type PublicActivityEvent } from "./group-events";

interface MessagesProps {
  readonly events: readonly PublicActivityEvent[];
}

/** OpenHands Messages grouping/presentation mechanics for public activity events. */
export const Messages = React.memo(
  ({ events }: MessagesProps) => {
    const renderedItems = React.useMemo(() => groupEvents(events), [events]);

    return (
      <>
        {renderedItems.map((item, itemIndex) => {
          if (item.kind === "single") {
            return <EventMessage key={item.event.id} event={item.event} />;
          }

          return (
            <EventGroup
              key={`group-${item.events[0]?.id ?? item.startIndex}`}
              events={item.events}
              isFinalized={itemIndex < renderedItems.length - 1}
            >
              {item.events.map((event) => (
                <EventMessage key={event.id} event={event} />
              ))}
            </EventGroup>
          );
        })}
      </>
    );
  },
  (previous, next) => {
    if (previous.events.length !== next.events.length) return false;
    return previous.events.every((event, index) => {
      const nextEvent = next.events[index];
      return (
        event.id === nextEvent?.id &&
        event.kind === nextEvent.kind &&
        event.title === nextEvent.title &&
        event.status === nextEvent.status &&
        event.detail === nextEvent.detail &&
        event.groupId === nextEvent.groupId
      );
    });
  },
);

Messages.displayName = "Messages";

interface ActivitySurfaceProps {
  readonly events?: readonly PublicActivityEvent[];
}

/**
 * Activity list composition keeps the upstream scroll-to-tail behavior while
 * leaving event ownership to a future runtime adapter.
 */
export function ActivitySurface({ events = [] }: ActivitySurfaceProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  const stickToEndRef = React.useRef(true);

  const handleScroll = () => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    stickToEndRef.current =
      scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 32;
  };

  React.useLayoutEffect(() => {
    if (!stickToEndRef.current) return;
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [events.length]);

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto p-5"
      role="log"
      aria-label="Agent 活动"
      aria-live="polite"
      onScroll={handleScroll}
    >
      {events.length === 0 ? (
        <div className="space-y-5">
          <div className="oh-empty-state">
            <p className="text-sm font-semibold">尚无 Agent 活动</p>
            <p>提交任务后，公开可审计的操作与进度会显示在这里。</p>
          </div>
          <CollapsibleRationale summary="查看活动公开范围">
            这里只展示公开操作、进度、限制与可审计依据，不接收模型私有推理。
          </CollapsibleRationale>
        </div>
      ) : (
        <Messages events={events} />
      )}
      <div ref={endRef} aria-hidden="true" />
    </div>
  );
}
