import React from "react";

import { useGripResize } from "../../../hooks/chat/use-grip-resize";

import { ChatInputContainer } from "./components/chat-input-container";
import { ChatInputGrip } from "./components/chat-input-grip";

interface CustomChatInputProps {
  readonly disabled?: boolean;
  readonly submitting?: boolean;
  readonly onSubmit: (message: string) => Promise<void>;
  readonly onFocus?: () => void;
  readonly onBlur?: () => void;
}

export function CustomChatInput({
  disabled = false,
  submitting = false,
  onSubmit,
  onFocus,
  onBlur,
}: CustomChatInputProps) {
  const [canSubmit, setCanSubmit] = React.useState(false);
  const chatInputRef = React.useRef<HTMLDivElement>(null);
  const chatContainerRef = React.useRef<HTMLDivElement>(null);
  const {
    height,
    currentHeight,
    minHeight,
    maxHeight,
    gripRef,
    isGripVisible,
    isGripDragging,
    handleTopEdgeClick,
    handleGripMouseDown,
    handleGripKeyDown,
    resizeToContent,
    resetHeight,
  } = useGripResize(chatInputRef, chatContainerRef);

  const syncCanSubmit = React.useCallback(() => {
    setCanSubmit(Boolean(chatInputRef.current?.textContent?.trim()));
  }, []);

  const handleSubmit = React.useCallback(async () => {
    const message = chatInputRef.current?.textContent?.trim() ?? "";
    if (!message || disabled || submitting) return;
    try {
      await onSubmit(message);
      if (chatInputRef.current) chatInputRef.current.textContent = "";
      setCanSubmit(false);
      resetHeight();
    } catch {
      chatInputRef.current?.focus();
    }
  }, [disabled, onSubmit, resetHeight, submitting]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  const handlePaste = (event: React.ClipboardEvent) => {
    const text = event.clipboardData.getData("text/plain");
    if (!text) return;
    event.preventDefault();
    const input = chatInputRef.current;
    if (!input) return;

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      input.append(document.createTextNode(text));
    } else {
      const range = selection.getRangeAt(0);
      if (!input.contains(range.commonAncestorContainer)) {
        input.append(document.createTextNode(text));
      } else {
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
    requestAnimationFrame(() => {
      syncCanSubmit();
      resizeToContent();
    });
  };

  const handleInput = React.useCallback(() => {
    syncCanSubmit();
    resizeToContent();
  }, [resizeToContent, syncCanSubmit]);

  return (
    <div
      className="group relative w-full"
      style={{ height: height ?? undefined, maxHeight }}
    >
      <ChatInputGrip
        gripRef={gripRef}
        isGripVisible={isGripVisible}
        isGripDragging={isGripDragging}
        value={currentHeight}
        min={minHeight}
        max={maxHeight}
        handleTopEdgeClick={handleTopEdgeClick}
        handleGripMouseDown={handleGripMouseDown}
        handleGripKeyDown={handleGripKeyDown}
      />
      <ChatInputContainer
        chatContainerRef={chatContainerRef}
        disabled={disabled}
        canSubmit={canSubmit}
        submitting={submitting}
        chatInputRef={chatInputRef}
        handleSubmit={() => void handleSubmit()}
        onInput={handleInput}
        onPaste={handlePaste}
        onKeyDown={handleKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      />
    </div>
  );
}
