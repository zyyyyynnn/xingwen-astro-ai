import React from "react";

const MIN_HEIGHT = 56;
const MAX_HEIGHT = 240;
const DEFAULT_HEIGHT = 56;
const KEYBOARD_STEP = 16;
const DEFAULT_LINE_HEIGHT = 24;

function clampHeight(height: number) {
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, height));
}

/** Composer resize mechanics retained from the upstream grip interaction. */
export function useGripResize(
  contentRef: React.RefObject<HTMLDivElement | null>,
) {
  const [height, setHeight] = React.useState(DEFAULT_HEIGHT);
  const [isGripVisible, setIsGripVisible] = React.useState(false);
  const [isGripDragging, setIsGripDragging] = React.useState(false);
  const gripRef = React.useRef<HTMLDivElement>(null);
  const dragStartRef = React.useRef({ pointerY: 0, height: DEFAULT_HEIGHT });
  const suppressNextTopEdgeClickRef = React.useRef(false);
  const isManuallySizedRef = React.useRef(false);

  const handleTopEdgeClick = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (suppressNextTopEdgeClickRef.current) {
      suppressNextTopEdgeClickRef.current = false;
      event.preventDefault();
      return;
    }
    if (!isGripDragging) setIsGripVisible((current) => !current);
  };

  const handleGripMouseDown = (event: React.MouseEvent) => {
    event.preventDefault();
    isManuallySizedRef.current = true;
    dragStartRef.current = { pointerY: event.clientY, height };
    setIsGripVisible(true);
    setIsGripDragging(true);
  };

  React.useLayoutEffect(() => {
    if (!isGripDragging) return undefined;

    const handleMouseMove = (event: MouseEvent) => {
      const delta = dragStartRef.current.pointerY - event.clientY;
      setHeight(clampHeight(dragStartRef.current.height + delta));
    };
    const handleMouseUp = () => {
      setIsGripDragging(false);
      suppressNextTopEdgeClickRef.current = true;
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isGripDragging]);

  const handleGripKeyDown = (event: React.KeyboardEvent) => {
    let nextHeight: number | undefined;
    if (event.key === "ArrowUp") nextHeight = height + KEYBOARD_STEP;
    if (event.key === "ArrowDown") nextHeight = height - KEYBOARD_STEP;
    if (event.key === "Home") nextHeight = MIN_HEIGHT;
    if (event.key === "End") nextHeight = MAX_HEIGHT;
    if (nextHeight === undefined) return;

    event.preventDefault();
    isManuallySizedRef.current = true;
    setHeight(clampHeight(nextHeight));
    setIsGripVisible(true);
  };

  const resizeToContent = React.useCallback(() => {
    const content = contentRef.current;
    if (!content || isManuallySizedRef.current) return;

    const contentHeight = content.scrollHeight;
    if (contentHeight <= 0) return;

    const lineHeight =
      typeof window === "undefined"
        ? DEFAULT_LINE_HEIGHT
        : Number.parseFloat(window.getComputedStyle(content).lineHeight) ||
          DEFAULT_LINE_HEIGHT;
    const nextHeight = clampHeight(
      DEFAULT_HEIGHT + Math.max(0, contentHeight - lineHeight),
    );
    setHeight((current) => (current === nextHeight ? current : nextHeight));
  }, [contentRef]);

  const resetHeight = React.useCallback(() => {
    isManuallySizedRef.current = false;
    setHeight(DEFAULT_HEIGHT);
  }, []);

  return {
    height,
    minHeight: MIN_HEIGHT,
    maxHeight: MAX_HEIGHT,
    gripRef,
    isGripVisible,
    isGripDragging,
    handleTopEdgeClick,
    handleGripMouseDown,
    handleGripKeyDown,
    resizeToContent,
    resetHeight,
  };
}
