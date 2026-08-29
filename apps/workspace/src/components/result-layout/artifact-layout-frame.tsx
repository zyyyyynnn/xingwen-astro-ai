import type { ReactNode } from "react";
import type { ArtifactLayoutMode } from "../../presentation/artifact-renderer-registry";

export interface ArtifactLayoutFrameProps {
  readonly mode: ArtifactLayoutMode;
  readonly children: ReactNode;
  readonly className?: string;
}

export function ArtifactLayoutFrame({
  mode,
  children,
  className = "",
}: ArtifactLayoutFrameProps) {
  return (
    <div
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
        <div className="xw-data-layout flex h-full min-h-0 w-full flex-col overflow-y-auto px-6 py-4">
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
