import type { ComponentProps } from "react";

import { cn } from "#utils";

export function Empty({ className, ...props }: ComponentProps<"div">) {
  return (
    <div data-slot="empty" className={cn("xw-empty", className)} {...props} />
  );
}

export function EmptyHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="empty-header"
      className={cn("xw-empty__header", className)}
      {...props}
    />
  );
}

export function EmptyMedia({
  className,
  variant = "default",
  ...props
}: ComponentProps<"div"> & { variant?: "default" | "icon" }) {
  return (
    <div
      data-slot="empty-media"
      data-variant={variant}
      className={cn("xw-empty__media", className)}
      {...props}
    />
  );
}

export function EmptyTitle({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="empty-title"
      className={cn("xw-empty__title", className)}
      {...props}
    />
  );
}

export function EmptyDescription({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="empty-description"
      className={cn("xw-empty__description", className)}
      {...props}
    />
  );
}
