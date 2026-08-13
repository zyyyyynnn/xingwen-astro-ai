import type { ComponentProps } from "react";

import { cn } from "#utils";

import { LoaderCircle } from "./icons";

export function Spinner({
  className,
  ...props
}: ComponentProps<typeof LoaderCircle>) {
  return (
    <LoaderCircle
      data-slot="spinner"
      role="status"
      aria-label="加载中"
      className={cn("xw-spinner", className)}
      {...props}
    />
  );
}
