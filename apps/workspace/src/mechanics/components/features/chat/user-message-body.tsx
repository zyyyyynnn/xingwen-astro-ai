import React from "react";

import { cn } from "../../../utils/utils";

const USER_MESSAGE_MAX_LINES = 5;
const USER_MESSAGE_LENGTH_THRESHOLD = 360;

/** OpenHands long-user-message collapse mechanic over public plain text. */
export function UserMessageBody({
  message,
  expanded,
  onTruncatableChange,
}: {
  readonly message: string;
  readonly expanded: boolean;
  readonly onTruncatableChange: (truncatable: boolean) => void;
}) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [truncatable, setTruncatable] = React.useState(false);

  React.useEffect(
    () => onTruncatableChange(truncatable),
    [onTruncatableChange, truncatable],
  );

  React.useLayoutEffect(() => {
    const content = contentRef.current;
    if (!content || expanded) {
      setTruncatable(false);
      return undefined;
    }
    const measure = () => {
      const measured = Number.parseFloat(getComputedStyle(content).lineHeight);
      const exceedsMeasuredHeight =
        Number.isFinite(measured) &&
        measured > 0 &&
        content.scrollHeight > USER_MESSAGE_MAX_LINES * measured + 1;
      setTruncatable(
        exceedsMeasuredHeight ||
          (message.match(/\n/g) ?? []).length >= USER_MESSAGE_MAX_LINES ||
          message.trim().length > USER_MESSAGE_LENGTH_THRESHOLD,
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    return () => observer.disconnect();
  }, [expanded, message]);

  const collapsed = truncatable && !expanded;
  return (
    <div className="relative min-w-0">
      <div
        ref={contentRef}
        className={cn(
          "chat-message__user-body min-w-0 whitespace-pre-wrap [word-break:break-word]",
          collapsed && "line-clamp-5",
        )}
      >
        {message}
      </div>
      {collapsed ? (
        <>
          <div aria-hidden="true" className="chat-message__collapse-fade" />
          <span className="chat-message__expand-label">展开</span>
        </>
      ) : null}
    </div>
  );
}
