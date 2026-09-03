import React, { type ReactNode } from "react";
import { MessageSquareText } from "@xingwen/ui/icons";

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
      data-message-type={type}
      className={cn(
        "chat-message",
        children && "chat-message--with-content",
        type === "user" && "chat-message--user",
        type === "agent" && "chat-message--agent",
        pendingStatus === "sending" && "chat-message--sending",
        pendingStatus === "error" && "chat-message--error",
        interactive && type === "agent" && "chat-message--interactive",
      )}
    >
      {type === "agent" && message ? (
        <div className="chat-message__agent-label">
          <MessageSquareText aria-hidden="true" />
          <span>星文分析</span>
        </div>
      ) : null}
      {type === "user" && pendingStatus === undefined ? (
        <UserMessageBody
          message={message}
          expanded={expanded}
          onTruncatableChange={handleTruncatableChange}
        />
      ) : (
        <div className="chat-message__body min-w-0 whitespace-pre-wrap [word-break:break-word]">
          {message}
        </div>
      )}
      {collapsed ? (
        <button
          type="button"
          className="chat-message__expand-hit-area"
          aria-label="展开完整研究消息"
          onClick={() => setExpansion({ message, expanded: true })}
        />
      ) : null}
      {children}
      {pendingStatus === "sending" ? (
        <span className="chat-message__pending">正在发送…</span>
      ) : null}
    </article>
  );
}
