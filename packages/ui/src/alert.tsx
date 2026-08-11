import type { ComponentProps } from "react";

import { cn } from "#utils";

export function Alert({
  className,
  variant = "default",
  ...props
}: ComponentProps<"div"> & { variant?: "default" | "destructive" }) {
  return (
    <div
      data-slot="alert"
      data-variant={variant}
      role="alert"
      className={cn("xw-alert", className)}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-title"
      className={cn("xw-alert__title", className)}
      {...props}
    />
  );
}

export function AlertDescription({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-description"
      className={cn("xw-alert__description", className)}
      {...props}
    />
  );
}
