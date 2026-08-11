import { useMemo, type ComponentProps } from "react";

import { cn } from "#utils";

export function FieldSet({ className, ...props }: ComponentProps<"fieldset">) {
  return (
    <fieldset
      data-slot="field-set"
      className={cn("xw-field-set", className)}
      {...props}
    />
  );
}

export function FieldLegend({
  className,
  variant = "legend",
  ...props
}: ComponentProps<"legend"> & { variant?: "legend" | "label" }) {
  return (
    <legend
      data-slot="field-legend"
      data-variant={variant}
      className={cn("xw-field-legend", className)}
      {...props}
    />
  );
}

export function FieldGroup({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="field-group"
      className={cn("xw-field-group", className)}
      {...props}
    />
  );
}

export function Field({
  className,
  orientation = "vertical",
  ...props
}: ComponentProps<"div"> & {
  orientation?: "vertical" | "horizontal" | "responsive";
}) {
  return (
    <div
      role="group"
      data-slot="field"
      data-orientation={orientation}
      className={cn("xw-field", className)}
      {...props}
    />
  );
}

export function FieldLabel({ className, ...props }: ComponentProps<"label">) {
  return (
    <label
      data-slot="field-label"
      className={cn("xw-field-label", className)}
      {...props}
    />
  );
}

export function FieldDescription({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="field-description"
      className={cn("xw-field-description", className)}
      {...props}
    />
  );
}

export function FieldError({
  className,
  children,
  errors,
  ...props
}: ComponentProps<"div"> & {
  errors?: Array<{ message?: string } | undefined>;
}) {
  const content = useMemo(() => {
    if (children) return children;
    const messages = [
      ...new Set(errors?.flatMap((item) => item?.message ?? [])),
    ];
    if (messages.length === 0) return null;
    if (messages.length === 1) return messages[0];
    return (
      <ul>
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    );
  }, [children, errors]);

  if (!content) return null;
  return (
    <div
      role="alert"
      data-slot="field-error"
      className={cn("xw-field-error", className)}
      {...props}
    >
      {content}
    </div>
  );
}
