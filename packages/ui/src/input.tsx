import type { ComponentProps } from "react";

import { cn } from "#utils";

export function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn("xw-input", className)}
      {...props}
    />
  );
}
