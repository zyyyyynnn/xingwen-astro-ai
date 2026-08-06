import {
  Provider as TooltipProvider,
  Root as TooltipRoot,
  Trigger as TooltipTrigger,
  Content as TooltipContent,
  Portal as TooltipPortal,
} from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export interface TooltipProps {
  readonly label: string;
  readonly children: ReactNode;
  readonly side?: "top" | "right" | "bottom" | "left";
}

export function Tooltip({ label, children, side = "top" }: TooltipProps) {
  return (
    <TooltipProvider delayDuration={300}>
      <TooltipRoot>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipPortal>
          <TooltipContent side={side} className="xw-tooltip__content">
            {label}
          </TooltipContent>
        </TooltipPortal>
      </TooltipRoot>
    </TooltipProvider>
  );
}
