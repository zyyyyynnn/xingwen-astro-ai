import React from "react";

const FALLBACK_ROOT_FONT_SIZE = 16;
const FALLBACK_UNBOUNDED_HEIGHT = Number.MAX_SAFE_INTEGER;

function getRootFontSize() {
  if (typeof document === "undefined") return FALLBACK_ROOT_FONT_SIZE;
  return (
    Number.parseFloat(
      window.getComputedStyle(document.documentElement).fontSize,
    ) || FALLBACK_ROOT_FONT_SIZE
  );
}

function getCssLengthInPixels(name: string, fallback: number) {
  if (typeof document === "undefined") return fallback;
  const value = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) return fallback;
  if (value.endsWith("rem")) return amount * getRootFontSize();
  if (value.endsWith("px")) return amount;
  return amount;
}

function clampHeight(height: number, minHeight: number, maxHeight: number) {
  return Math.min(maxHeight, Math.max(minHeight, height));
}

function getMeasuredHeight(
  containerRef: React.RefObject<HTMLDivElement | null>,
  contentRef: React.RefObject<HTMLDivElement | null>,
) {
  const containerHeight =
    containerRef.current?.getBoundingClientRect().height ?? 0;
  if (containerHeight > 0) return containerHeight;
  const contentHeight = contentRef.current?.getBoundingClientRect().height ?? 0;
  return contentHeight > 0 ? contentHeight : 0;
}

function getVerticalChromeHeight(
  container: HTMLDivElement,
  content: HTMLDivElement,
) {
  const styles = window.getComputedStyle(container);
  const padding =
    (Number.parseFloat(styles.paddingTop) || 0) +
    (Number.parseFloat(styles.paddingBottom) || 0);
  const border =
    (Number.parseFloat(styles.borderTopWidth) || 0) +
    (Number.parseFloat(styles.borderBottomWidth) || 0);
  const actions = container.querySelector<HTMLElement>(
    '[data-testid="chat-input-actions"]',
  );
  const actionHeight = actions?.getBoundingClientRect().height ?? 0;
  const contentHeight = content.getBoundingClientRect().height;
  const currentHeight = container.getBoundingClientRect().height;
  const observedChrome = currentHeight - contentHeight;

  return Math.max(padding + border + actionHeight, observedChrome, 0);
}

/** Composer resize mechanics retained from the upstream grip interaction. */
export function useGripResize(
  contentRef: React.RefObject<HTMLDivElement | null>,
  containerRef: React.RefObject<HTMLDivElement | null>,
) {
  const [explicitHeight, setExplicitHeight] = React.useState<number | null>(
    null,
  );
  const [naturalHeight, setNaturalHeight] = React.useState<number | null>(null);
  const [isGripVisible, setIsGripVisible] = React.useState(false);
  const [isGripDragging, setIsGripDragging] = React.useState(false);
  const gripRef = React.useRef<HTMLDivElement>(null);
  const dragStartRef = React.useRef({ pointerY: 0, height: 0 });
  const suppressNextTopEdgeClickRef = React.useRef(false);
  const isManuallySizedRef = React.useRef(false);

  const maxHeight = getCssLengthInPixels(
    "--workspace-composer-max-block-size",
    FALLBACK_UNBOUNDED_HEIGHT,
  );
  const keyboardStep = getCssLengthInPixels(
    "--workspace-composer-keyboard-step",
    getRootFontSize(),
  );

  const measureNaturalHeight = React.useCallback(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return;

    const measured = getMeasuredHeight(containerRef, contentRef);
    if (measured > 0) {
      setNaturalHeight((current) =>
        current === measured ? current : measured,
      );
      return;
    }

    const contentHeight = content.scrollHeight;
    if (contentHeight <= 0) return;
    const fallbackHeight =
      contentHeight + getVerticalChromeHeight(container, content);
    setNaturalHeight((current) =>
      current === fallbackHeight ? current : fallbackHeight,
    );
  }, [containerRef, contentRef]);

  React.useLayoutEffect(() => {
    measureNaturalHeight();
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return undefined;

    const observer = new ResizeObserver(() => {
      if (!isManuallySizedRef.current) measureNaturalHeight();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef, measureNaturalHeight]);

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
    dragStartRef.current = {
      pointerY: event.clientY,
      height:
        getMeasuredHeight(containerRef, contentRef) ||
        naturalHeight ||
        contentRef.current?.scrollHeight ||
        1,
    };
    setIsGripVisible(true);
    setIsGripDragging(true);
  };

  React.useLayoutEffect(() => {
    if (!isGripDragging) return undefined;

    const handleMouseMove = (event: MouseEvent) => {
      const delta = dragStartRef.current.pointerY - event.clientY;
      if (delta !== 0) isManuallySizedRef.current = true;
      if (delta === 0) return;
      const minHeight = naturalHeight ?? 0;
      setExplicitHeight(
        clampHeight(dragStartRef.current.height + delta, minHeight, maxHeight),
      );
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
  }, [isGripDragging, maxHeight, naturalHeight]);

  const handleGripKeyDown = (event: React.KeyboardEvent) => {
    const measuredHeight = getMeasuredHeight(containerRef, contentRef);
    const currentHeight =
      explicitHeight ??
      (measuredHeight ||
        naturalHeight ||
        contentRef.current?.scrollHeight ||
        1);
    const minHeight = naturalHeight ?? currentHeight;
    let nextHeight: number | undefined;
    if (event.key === "ArrowUp") nextHeight = currentHeight + keyboardStep;
    if (event.key === "ArrowDown") nextHeight = currentHeight - keyboardStep;
    if (event.key === "Home") nextHeight = minHeight;
    if (event.key === "End") nextHeight = maxHeight;
    if (nextHeight === undefined) return;

    event.preventDefault();
    isManuallySizedRef.current = true;
    setExplicitHeight(clampHeight(nextHeight, minHeight, maxHeight));
    setIsGripVisible(true);
  };

  const resizeToContent = React.useCallback(() => {
    if (isManuallySizedRef.current) return;
    setExplicitHeight(null);
    measureNaturalHeight();
  }, [measureNaturalHeight]);

  const resetHeight = React.useCallback(() => {
    isManuallySizedRef.current = false;
    setExplicitHeight(null);
    setNaturalHeight(null);
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(measureNaturalHeight);
    }
  }, [measureNaturalHeight]);

  return {
    height: explicitHeight,
    currentHeight: explicitHeight ?? naturalHeight ?? 0,
    minHeight: naturalHeight ?? 0,
    maxHeight,
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
