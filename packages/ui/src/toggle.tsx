"use client";

import * as React from "react";
import { Toggle as TogglePrimitive } from "radix-ui";

import { cn } from "#utils";

type ToggleVariant = "default" | "outline";
type ToggleSize = "default" | "sm" | "lg";
type ToggleVariantProps = {
  readonly variant?: ToggleVariant | null;
  readonly size?: ToggleSize | null;
};

const TOGGLE_VARIANT_CLASSES: Record<ToggleVariant, string> = {
  default: "bg-transparent",
  outline:
    "border border-input bg-transparent shadow-xs hover:bg-accent hover:text-accent-foreground",
};

const TOGGLE_SIZE_CLASSES: Record<ToggleSize, string> = {
  default: "h-9 min-w-9 px-2",
  sm: "h-8 min-w-8 px-1.5",
  lg: "h-10 min-w-10 px-2.5",
};

function toggleVariants({
  variant = "default",
  size = "default",
  className,
}: ToggleVariantProps & { readonly className?: string } = {}): string {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-[color,box-shadow] outline-none hover:bg-muted hover:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 data-[state=on]:bg-accent data-[state=on]:text-accent-foreground dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    TOGGLE_VARIANT_CLASSES[variant ?? "default"],
    TOGGLE_SIZE_CLASSES[size ?? "default"],
    className,
  );
}

function Toggle({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<typeof TogglePrimitive.Root> & ToggleVariantProps) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={toggleVariants({ variant, size, className })}
      {...props}
    />
  );
}

export { Toggle, toggleVariants };
export type { ToggleSize, ToggleVariant, ToggleVariantProps };
