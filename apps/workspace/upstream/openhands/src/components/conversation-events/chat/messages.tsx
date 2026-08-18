import React from "react";

import { EventGroup } from "./event-message-components/event-group";
import { EventMessage } from "./event-message";
import { groupEvents, type ActivityPresentationEvent } from "./group-events";

/**
 * OpenHands message-stream mechanics. Product data is projected into this
 * event shape by the research boundary; grouping and disclosure stay here.
 */
export const Messages = React.memo(function Messages({
  events,
  onOpenArtifactVersion,
}: {
  readonly events: readonly ActivityPresentationEvent[];
  readonly onOpenArtifactVersion?: Parameters<
    typeof EventMessage
  >[0]["onOpenArtifactVersion"];
}) {
  const renderedItems = React.useMemo(() => groupEvents(events), [events]);
  return (
    <>
      {renderedItems.map((item, index) =>
        item.kind === "single" ? (
          <EventMessage
            key={item.event.id}
            event={item.event}
            onOpenArtifactVersion={onOpenArtifactVersion}
          />
        ) : (
          <EventGroup
            key={`group-${item.events[0]?.id ?? item.startIndex}`}
            events={item.events}
            isFinalized={index < renderedItems.length - 1}
          >
            {item.events.map((event) => (
              <EventMessage
                key={event.id}
                event={event}
                onOpenArtifactVersion={onOpenArtifactVersion}
              />
            ))}
          </EventGroup>
        ),
      )}
    </>
  );
});
