import React from "react";

import { EventGroup } from "./event-message-components/event-group";
import { EventMessage } from "./event-message";
import { groupEvents, type ActivityPresentationEvent } from "./group-events";

/** OpenHands Messages grouping and event rendering mechanics. */
export const Messages = React.memo(function Messages({
  events,
}: {
  readonly events: readonly ActivityPresentationEvent[];
}) {
  const renderedItems = React.useMemo(() => groupEvents(events), [events]);
  return (
    <>
      {renderedItems.map((item, index) =>
        item.kind === "single" ? (
          <EventMessage key={item.event.id} event={item.event} />
        ) : (
          <EventGroup
            key={`group-${item.events[0]?.id ?? item.startIndex}`}
            events={item.events}
            isFinalized={index < renderedItems.length - 1}
          >
            {item.events.map((event) => (
              <EventMessage key={event.id} event={event} />
            ))}
          </EventGroup>
        ),
      )}
    </>
  );
});
