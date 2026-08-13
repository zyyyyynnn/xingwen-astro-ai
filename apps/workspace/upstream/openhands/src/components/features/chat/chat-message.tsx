import React, { type ReactNode } from "react";

import { cn } from "../../../utils/utils";
import { UserMessageBody } from "./user-message-body";

interface ChatMessageProps {
  readonly type: "user" | "agent";
  readonly message: string;
  readonly children?: ReactNode;
  readonly interactive?: boolean;
  readonly pendingStatus?: "sending" | "error";
}

/**
 * OpenHands ChatMessage composition with runtime-specific markdown, media and
 * branch actions removed. Research content is supplied through the renderer
 * boundary; bubble geometry and role hierarchy stay upstream-derived.
 */
export function ChatMessage({
  type,
  message,
  children,
  interactive = false,
  pendingStatus,
}: ChatMessageProps) {
  const [expansion, setExpansion] = React.useState({
    message,
    expanded: false,
  });
  const [truncation, setTruncation] = React.useState({
    message,
    truncatable: false,
  });
  const expanded = expansion.message === message && expansion.expanded;
  const truncatable = truncation.message === message && truncation.truncatable;
  const collapsed = type === "user" && truncatable && !expanded;
  const handleTruncatableChange = React.useCallback(
    (nextTruncatable: boolean) => {
      setTruncation((current) =>
        current.message === message && current.truncatable === nextTruncatable
          ? current
          : { message, truncatable: nextTruncatable },
      );
    },
    [message],
  );

  return (
    <article
      data-testid={`${type}-message`}
      className={cn(
        "relative flex w-fit max-w-[min(42rem,88%)] flex-col rounded-[var(--oh-radius-lg)]",
        children && "gap-2",
        type === "user" &&
          "mt-6 self-end bg-[var(--oh-surface-muted)] px-4 py-2.5",
        type === "agent" && "mt-6 w-full bg-transparent",
        interactive &&
          type === "agent" &&
          "mt-2 border border-[var(--oh-border)] bg-[var(--oh-surface)] p-4",
        pendingStatus === "sending" && "opacity-70",
        pendingStatus === "error" &&
          "border border-[var(--oh-status-error)]/40",
        "last:mb-4",
      )}
    >
      {type === "user" && pendingStatus === undefined ? (
        <UserMessageBody
          message={message}
          expanded={expanded}
          onTruncatableChange={handleTruncatableChange}
        />
      ) : (
        <div className="min-w-0 whitespace-pre-wrap text-sm leading-6 [word-break:break-word]">
          {message}
        </div>
      )}
      {collapsed ? (
        <button
          type="button"
          className="absolute inset-0 cursor-pointer rounded-[var(--oh-radius-lg)]"
          aria-label="展开完整研究消息"
          onClick={() => setExpansion({ message, expanded: true })}
        />
      ) : null}
      {children}
      {pendingStatus === "sending" ? (
        <span className="text-xs text-[var(--oh-muted)]">正在发送…</span>
      ) : null}
    </article>
  );
}
