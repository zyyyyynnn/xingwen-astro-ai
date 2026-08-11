import type { ComponentProps } from "react";

import { cn } from "#utils";

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn("xw-textarea", className)}
      {...props}
    />
  );
}
