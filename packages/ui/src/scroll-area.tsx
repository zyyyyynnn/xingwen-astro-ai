import {
  Corner,
  Root,
  ScrollAreaScrollbar,
  Thumb,
  Viewport,
} from "@radix-ui/react-scroll-area";
import type { ReactNode } from "react";

export interface ScrollAreaProps {
  readonly children: ReactNode;
  readonly className?: string;
  readonly viewportClassName?: string;
}

export function ScrollArea({
  children,
  className,
  viewportClassName,
}: ScrollAreaProps) {
  const combined = ["xw-scroll-area", className].filter(Boolean).join(" ");
  const viewportCombined = ["xw-scroll-area__viewport", viewportClassName]
    .filter(Boolean)
    .join(" ");
  return (
    <Root className={combined} type="auto">
      <Viewport className={viewportCombined}>{children}</Viewport>
      <ScrollAreaScrollbar
        className="xw-scroll-area__bar"
        orientation="vertical"
      >
        <Thumb className="xw-scroll-area__thumb" />
      </ScrollAreaScrollbar>
      <Corner />
    </Root>
  );
}
