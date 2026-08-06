import {
  Close,
  Content,
  Description,
  Overlay,
  Portal,
  Root,
  Title,
} from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export type SheetSide = "left" | "right" | "bottom";

export interface SheetProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly children: ReactNode;
}

export interface SheetContentProps {
  readonly side?: SheetSide;
  readonly children: ReactNode;
  readonly className?: string;
}

export interface SheetHeaderProps {
  readonly children: ReactNode;
}

export function Sheet({ open, onOpenChange, children }: SheetProps) {
  return (
    <Root open={open} onOpenChange={onOpenChange}>
      {children}
    </Root>
  );
}

export function SheetContent({
  side = "right",
  children,
  className,
}: SheetContentProps) {
  const combined = [
    "xw-sheet__content",
    `xw-sheet__content--${side}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <Portal>
      <Overlay className="xw-sheet__overlay" />
      <Content className={combined}>{children}</Content>
    </Portal>
  );
}

export function SheetHeader({ children }: SheetHeaderProps) {
  return <div className="xw-sheet__header">{children}</div>;
}

export function SheetTitle({ children }: { children: ReactNode }) {
  return <Title className="xw-sheet__title">{children}</Title>;
}

export function SheetDescription({ children }: { children: ReactNode }) {
  return (
    <Description className="xw-sheet__description">{children}</Description>
  );
}

export function SheetClose({ children }: { children: ReactNode }) {
  return <Close className="xw-sheet__close">{children}</Close>;
}
