import * as React from "react";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";

import { cn } from "#utils";

type ToggleVariant = "default" | "outline" | "segmented";
type ToggleSize = "default" | "sm" | "lg";
type ToggleVariantProps = {
  readonly variant?: ToggleVariant | null;
  readonly size?: ToggleSize | null;
};

type ToggleSpacing = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8;

const ToggleGroupContext = React.createContext<
  ToggleVariantProps & { readonly spacing?: ToggleSpacing }
>({});

function ToggleGroup({
  className,
  variant,
  size,
  spacing = 0,
  orientation = "horizontal",
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root> &
  ToggleVariantProps & { readonly spacing?: ToggleSpacing }) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      data-variant={variant ?? "default"}
      data-size={size ?? "default"}
      data-spacing={spacing}
      data-orientation={orientation}
      orientation={orientation}
      className={cn("xw-toggle-group", className)}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ variant, size, spacing }}>
        {children}
      </ToggleGroupContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({
  className,
  children,
  variant,
  size,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item> &
  ToggleVariantProps) {
  const context = React.useContext(ToggleGroupContext);

  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      data-variant={context.variant ?? variant ?? "default"}
      data-size={context.size ?? size ?? "default"}
      data-spacing={context.spacing}
      className={cn("xw-toggle-group__item", className)}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
}

export { ToggleGroup, ToggleGroupItem };
