import { useLayoutEffect, useRef, type ReactNode } from "react";
import type { ArtifactLayoutMode } from "../../presentation/artifact-renderer-registry";

export interface ArtifactLayoutFrameProps {
  readonly mode: ArtifactLayoutMode;
  readonly children: ReactNode;
  readonly className?: string;
  readonly scrollKey?: string;
}

export function ArtifactLayoutFrame({
  mode,
  children,
  className = "",
  scrollKey,
}: ArtifactLayoutFrameProps) {
  const frameRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    frame.scrollTop = 0;
    frame.scrollLeft = 0;
    for (const container of frame.querySelectorAll<HTMLElement>(
      "[data-artifact-scroll-container]",
    )) {
      container.scrollTop = 0;
      container.scrollLeft = 0;
    }
  }, [scrollKey]);

  return (
    <div
      ref={frameRef}
      className={`xw-artifact-layout-frame xw-artifact-layout-frame--${mode} ${className}`}
      data-layout-mode={mode}
    >
      {mode === "reading" ? (
        <div className="xw-reading-column mx-auto w-full max-w-[var(--workspace-result-reading-max-inline-size)] px-6 py-6">
          {children}
        </div>
      ) : mode === "wide" ? (
        <div className="xw-wide-column mx-auto w-full max-w-[var(--workspace-result-wide-max-inline-size)] px-6 py-6">
          {children}
        </div>
      ) : mode === "data" ? (
        <div
          className="xw-data-layout flex h-full min-h-0 w-full flex-col overflow-y-auto px-6 py-4"
          data-artifact-scroll-container
        >
          {children}
        </div>
      ) : mode === "graph" ? (
        <div className="xw-graph-layout flex h-full min-h-0 w-full flex-col overflow-hidden">
          {children}
        </div>
      ) : (
        <div className="xw-immersive-layout h-full min-h-0 w-full overflow-hidden">
          {children}
        </div>
      )}
    </div>
  );
}
