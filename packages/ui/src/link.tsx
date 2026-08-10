import type { AnchorHTMLAttributes } from "react";

import { cn } from "#utils";

export type LinkVariant = "text" | "button";

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  external?: boolean;
  variant?: LinkVariant;
}

export function Link({
  external,
  variant = "text",
  className,
  ...props
}: LinkProps) {
  const combined = cn("xw-link", `xw-link--${variant}`, className);
  const externalProps = external
    ? { target: "_blank", rel: "noopener noreferrer" }
    : {};
  return (
    <a
      data-slot="link"
      data-variant={variant}
      className={combined}
      {...externalProps}
      {...props}
    />
  );
}
