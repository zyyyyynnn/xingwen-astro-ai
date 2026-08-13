import type { ComponentProps } from "react";

import { cn } from "#utils";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("xw-skeleton", className)}
      {...props}
    />
  );
}
