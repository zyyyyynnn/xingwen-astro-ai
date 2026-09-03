import * as React from "react";
import { Accordion as AccordionPrimitive } from "radix-ui";

import { cn } from "#utils";
import { ChevronDown as ChevronDownIcon } from "./icons";

function Accordion({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Root>) {
  return (
    <AccordionPrimitive.Root
      data-slot="accordion"
      className={cn("xw-accordion", className)}
      {...props}
    />
  );
}

function AccordionItem({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Item>) {
  return (
    <AccordionPrimitive.Item
      data-slot="accordion-item"
      className={cn("xw-accordion__item", className)}
      {...props}
    />
  );
}

function AccordionTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="xw-accordion__header">
      <AccordionPrimitive.Trigger
        data-slot="accordion-trigger"
        className={cn("xw-accordion__trigger", className)}
        {...props}
      >
        {children}
        <ChevronDownIcon
          data-icon="inline-end"
          className="xw-accordion__chevron"
          aria-hidden="true"
        />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  );
}

function AccordionContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content
      data-slot="accordion-content"
      className="xw-accordion__content"
      {...props}
    >
      <div className={cn("xw-accordion__body", className)}>{children}</div>
    </AccordionPrimitive.Content>
  );
}

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
