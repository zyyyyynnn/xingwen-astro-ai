import type { ComponentProps } from "react";

import { cn } from "#utils";

/**
 * Source: shadcn/ui `card` (MIT), adapted to Xingwen semantic tokens and the
 * repository's explicit compact size contract.
 */
export type CardSize = "default" | "small";

export function Card({
  className,
  size = "default",
  ...props
}: ComponentProps<"div"> & { readonly size?: CardSize }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cn("xw-card", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("xw-card__header", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("xw-card__title", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("xw-card__description", className)}
      {...props}
    />
  );
}

export function CardAction({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("xw-card__action", className)}
      {...props}
    />
  );
}

export function CardContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("xw-card__content", className)}
      {...props}
    />
  );
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("xw-card__footer", className)}
      {...props}
    />
  );
}
