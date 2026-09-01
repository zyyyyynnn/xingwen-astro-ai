import type { ButtonHTMLAttributes } from "react";

import { cn } from "#utils";

/**
 * Source: shadcn/ui `button` (MIT), adapted to Xingwen semantic tokens and
 * clsx-based class composition. Radix Slot/asChild and class-variance-authority
 * are intentionally omitted because current production consumers use native
 * button and anchor controls.
 * See ../component-sources.json for the reviewed source and consumers.
 */
export type ButtonVariant =
  "primary" | "secondary" | "outline" | "ghost" | "destructive" | "link";
export type ButtonSize =
  | "default"
  | "xsmall"
  | "small"
  | "large"
  | "inline"
  | "icon"
  | "icon-small"
  | "icon-xsmall";

type NativeButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
>;

interface TextButtonProps extends NativeButtonProps {
  variant?: ButtonVariant;
  size?: Exclude<ButtonSize, "icon" | "icon-small" | "icon-xsmall">;
  "aria-label"?: string;
}

interface IconButtonProps extends NativeButtonProps {
  variant?: ButtonVariant;
  size: "icon" | "icon-small" | "icon-xsmall";
  "aria-label": string;
}

export type ButtonProps = TextButtonProps | IconButtonProps;

export interface ButtonClassNameOptions {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly className?: string;
}

export function buttonClassName({
  variant = "primary",
  size = "default",
  className,
}: ButtonClassNameOptions = {}) {
  return cn(
    "xw-button",
    `xw-button--${variant}`,
    `xw-button--${size}`,
    className,
  );
}

export function Button({
  variant = "primary",
  size = "default",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={buttonClassName({ variant, size, className })}
      {...props}
    />
  );
}
