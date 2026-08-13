import * as React from "react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";

import { Check as CheckIcon } from "./icons";
import { cn } from "#utils";

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn("xw-checkbox", className)}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="xw-checkbox__indicator"
      >
        <CheckIcon aria-hidden="true" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
