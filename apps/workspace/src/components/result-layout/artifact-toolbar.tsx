import type { ReactNode } from "react";

export interface ArtifactToolbarProps {
  readonly left?: ReactNode;
  readonly right?: ReactNode;
  readonly children?: ReactNode;
  readonly className?: string;
}

export function ArtifactToolbar({
  left = null,
  right = null,
  children = null,
  className = "",
}: ArtifactToolbarProps) {
  return (
    <div
      className={`xw-artifact-toolbar flex flex-wrap items-center justify-between gap-3 ${className}`}
      role="toolbar"
      aria-label="结果操作栏"
    >
      <div className="flex flex-wrap items-center gap-3">
        {left}
        {children}
      </div>
      <div className="flex flex-wrap items-center gap-2">{right}</div>
    </div>
  );
}
