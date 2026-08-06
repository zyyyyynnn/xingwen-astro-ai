import { Content, Root, Trigger } from "@radix-ui/react-collapsible";
import type { ReactNode } from "react";

export interface CollapsibleProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly children: ReactNode;
}

export function Collapsible({
  open,
  onOpenChange,
  children,
}: CollapsibleProps) {
  return (
    <Root open={open} onOpenChange={onOpenChange}>
      {children}
    </Root>
  );
}

export function CollapsibleTrigger({ children }: { children: ReactNode }) {
  return <Trigger asChild>{children}</Trigger>;
}

export function CollapsibleContent({ children }: { children: ReactNode }) {
  return <Content className="xw-collapsible__content">{children}</Content>;
}
