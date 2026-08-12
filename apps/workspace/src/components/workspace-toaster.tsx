import { clsx } from "clsx";
import type { CSSProperties } from "react";
import { Toaster as Sonner, toast, type ToasterProps } from "sonner";

import {
  CheckCircle2,
  CircleX,
  Info,
  LoaderCircle,
  TriangleAlert,
} from "@xingwen/ui/icons";

/**
 * shadcn Sonner registry component adapted at the application composition
 * boundary so transient feedback does not leak runtime state into @xingwen/ui.
 */
const WorkspaceToaster = ({ className, ...props }: ToasterProps) => (
  <Sonner
    theme="system"
    position="bottom-right"
    className={clsx("xw-toaster group", className)}
    icons={{
      success: <CheckCircle2 aria-hidden="true" />,
      info: <Info aria-hidden="true" />,
      warning: <TriangleAlert aria-hidden="true" />,
      error: <CircleX aria-hidden="true" />,
      loading: (
        <LoaderCircle
          className="animate-spin motion-reduce:animate-none"
          aria-hidden="true"
        />
      ),
    }}
    style={
      {
        "--normal-bg": "var(--color-surface)",
        "--normal-text": "var(--color-ink-primary)",
        "--normal-border": "var(--color-border)",
        "--border-radius": "var(--radius-md)",
      } as CSSProperties
    }
    {...props}
  />
);

export { WorkspaceToaster, toast };
