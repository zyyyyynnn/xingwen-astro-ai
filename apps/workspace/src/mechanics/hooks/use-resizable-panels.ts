import React from "react";

interface UseResizablePanelsOptions {
  readonly defaultLeftWidth: number;
  readonly minLeftWidth: number;
  readonly maxLeftWidth: number;
  readonly keyboardStep: number;
  readonly storageKey?: string;
}

export function useResizablePanels({
  defaultLeftWidth,
  minLeftWidth,
  maxLeftWidth,
  keyboardStep,
  storageKey = "desktop-layout-panel-width",
}: UseResizablePanelsOptions) {
  const clampWidth = React.useCallback(
    (width: number) => Math.max(minLeftWidth, Math.min(maxLeftWidth, width)),
    [maxLeftWidth, minLeftWidth],
  );
  const [leftWidth, setLeftWidth] = React.useState(() => {
    if (typeof window === "undefined") return defaultLeftWidth;
    const stored = Number(window.localStorage.getItem(storageKey));
    return clampWidth(
      Number.isFinite(stored) && stored > 0 ? stored : defaultLeftWidth,
    );
  });
  const leftWidthRef = React.useRef(leftWidth);
  const [isDragging, setIsDragging] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);

  const persistWidth = React.useCallback(
    (width: number) => window.localStorage.setItem(storageKey, String(width)),
    [storageKey],
  );

  const handleMouseDown = React.useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = React.useCallback(
    (event: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.width === 0) return;
      const nextWidth = clampWidth(
        ((event.clientX - rect.left) / rect.width) * 100,
      );
      leftWidthRef.current = nextWidth;
      setLeftWidth(nextWidth);
    },
    [clampWidth, isDragging],
  );

  const handleMouseUp = React.useCallback(() => {
    if (!isDragging) return;
    setIsDragging(false);
    persistWidth(leftWidthRef.current);
  }, [isDragging, persistWidth]);

  React.useLayoutEffect(() => {
    if (!isDragging) return undefined;
    const shield = document.createElement("div");
    shield.setAttribute("aria-hidden", "true");
    shield.dataset.panelDragShield = "";
    Object.assign(shield.style, {
      position: "fixed",
      inset: "0",
      zIndex: "var(--oh-layer-panel-drag-shield)",
      cursor: "ew-resize",
    });
    document.body.appendChild(shield);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      shield.remove();
    };
  }, [handleMouseMove, handleMouseUp, isDragging]);

  const handleKeyboardResize = React.useCallback(
    (direction: -1 | 1) => {
      setLeftWidth((current) => {
        const next = clampWidth(current + direction * keyboardStep);
        leftWidthRef.current = next;
        persistWidth(next);
        return next;
      });
    },
    [clampWidth, keyboardStep, persistWidth],
  );

  return {
    leftWidth,
    rightWidth: 100 - leftWidth,
    minLeftWidth,
    maxLeftWidth,
    isDragging,
    containerRef,
    handleMouseDown,
    handleKeyboardResize,
  };
}
