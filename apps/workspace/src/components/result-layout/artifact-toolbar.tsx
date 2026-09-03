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
      className={`xw-artifact-toolbar ${className}`}
      role="toolbar"
      aria-label="结果操作栏"
    >
      <div className="xw-artifact-toolbar__group">
        {left}
        {children}
      </div>
      <div className="xw-artifact-toolbar__actions">{right}</div>
    </div>
  );
}
