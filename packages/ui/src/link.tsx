import type { AnchorHTMLAttributes } from "react";

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
  const combined = ["xw-link", `xw-link--${variant}`, className]
    .filter(Boolean)
    .join(" ");
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
