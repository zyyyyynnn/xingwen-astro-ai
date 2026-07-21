import type { AnchorHTMLAttributes } from "react";

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  external?: boolean;
}

export function Link({ external, className, ...props }: LinkProps) {
  const combined = ["xw-link", className].filter(Boolean).join(" ");
  const externalProps = external
    ? { target: "_blank", rel: "noopener noreferrer" }
    : {};
  return <a className={combined} {...externalProps} {...props} />;
}
