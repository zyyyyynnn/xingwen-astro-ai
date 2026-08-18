import React, { type ReactNode } from "react";

import { useGripResize } from "../../../hooks/chat/use-grip-resize";

import { ChatInputContainer } from "./components/chat-input-container";
import { ChatInputGrip } from "./components/chat-input-grip";

interface CustomChatInputProps {
  readonly disabled?: boolean;
  readonly submitting?: boolean;
  readonly value: string;
  readonly placeholder: string;
  readonly leadingActions: ReactNode;
  readonly onValueChange: (value: string) => void;
  readonly onSubmit: (message: string) => Promise<void>;
  readonly onFilesSelected?: (files: readonly File[]) => void;
  readonly onDragOver?: () => void;
  readonly onDragLeave?: () => void;
  readonly onDropFiles?: (files: readonly File[]) => void;
  readonly dragActive?: boolean;
}

export function CustomChatInput({
  disabled = false,
  submitting = false,
  value,
  placeholder,
  leadingActions,
  onValueChange,
  onSubmit,
  onFilesSelected,
  onDragOver,
  onDragLeave,
  onDropFiles,
  dragActive = false,
}: CustomChatInputProps) {
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

  React.useLayoutEffect(() => {
    const input = chatInputRef.current;
    if (input && input.textContent !== value) input.textContent = value;
  }, [value]);

  const syncValue = React.useCallback(() => {
    onValueChange(chatInputRef.current?.textContent ?? "");
    resizeToContent();
  }, [onValueChange, resizeToContent]);

  const handleSubmit = React.useCallback(async () => {
    const message = chatInputRef.current?.textContent?.trim() ?? "";
    if (!message || disabled || submitting) return;
    try {
      await onSubmit(message);
      onValueChange("");
      if (chatInputRef.current) chatInputRef.current.textContent = "";
      resetHeight();
    } catch {
      chatInputRef.current?.focus();
    }
  }, [disabled, onSubmit, onValueChange, resetHeight, submitting]);

  const handlePaste = (event: React.ClipboardEvent) => {
    const files = Array.from(event.clipboardData.files ?? []);
    if (files.length > 0) {
      event.preventDefault();
      onFilesSelected?.(files);
      return;
    }
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
    requestAnimationFrame(syncValue);
  };

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
        canSubmit={value.trim().length > 0}
        submitting={submitting}
        chatInputRef={chatInputRef}
        placeholder={placeholder}
        leadingActions={leadingActions}
        handleSubmit={() => void handleSubmit()}
        onInput={syncValue}
        onPaste={handlePaste}
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            void handleSubmit();
          }
        }}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={(event) => {
          event.preventDefault();
          onDragLeave?.();
          onDropFiles?.(Array.from(event.dataTransfer.files));
        }}
        dragActive={dragActive}
      />
    </div>
  );
}
