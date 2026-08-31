import * as React from "react";
import { Slot } from "radix-ui";

import { Separator } from "#components/separator";
import { cn } from "#utils";

type ItemVariant = "default" | "outline" | "muted";
type ItemSize = "default" | "sm";
type ItemMediaVariant = "default" | "icon" | "image";

function ItemGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-group"
      className={cn("xw-item-group", className)}
      {...props}
    />
  );
}

function ItemSeparator({
  className,
  ...props
}: React.ComponentProps<typeof Separator>) {
  return (
    <Separator
      data-slot="item-separator"
      orientation="horizontal"
      className={cn("xw-item-separator", className)}
      {...props}
    />
  );
}

function Item({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"div"> & {
  readonly variant?: ItemVariant;
  readonly size?: ItemSize;
  readonly asChild?: boolean;
}) {
  const Comp = asChild ? Slot.Root : "div";
  return (
    <Comp
      data-slot="item"
      data-variant={variant}
      data-size={size}
      className={cn("xw-item", className)}
      {...props}
    />
  );
}

function ItemMedia({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & { readonly variant?: ItemMediaVariant }) {
  return (
    <div
      data-slot="item-media"
      data-variant={variant}
      className={cn("xw-item__media", className)}
      {...props}
    />
  );
}

function ItemContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-content"
      className={cn("xw-item__content", className)}
      {...props}
    />
  );
}

function ItemTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-title"
      className={cn("xw-item__title", className)}
      {...props}
    />
  );
}

function ItemDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="item-description"
      className={cn("xw-item__description", className)}
      {...props}
    />
  );
}

function ItemActions({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-actions"
      className={cn("xw-item__actions", className)}
      {...props}
    />
  );
}

export {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemSeparator,
  ItemTitle,
};
