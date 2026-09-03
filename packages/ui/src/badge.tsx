import type { ComponentProps } from "react";

import { cn } from "#utils";

export type BadgeVariant =
  "default" | "secondary" | "destructive" | "outline" | "ghost";

export function Badge({
  className,
  variant = "default",
  ...props
}: ComponentProps<"span"> & { variant?: BadgeVariant }) {
  return (
    <span
      data-slot="badge"
      data-variant={variant}
      className={cn("xw-badge", className)}
      {...props}
    />
  );
}
