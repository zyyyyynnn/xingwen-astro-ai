import { clsx, type ClassValue } from "clsx";

/**
 * Merge class names with conditional support.
 *
 * This is the standard shadcn utility entry point for class composition.
 * It uses clsx for conditional joining; tailwind-merge is intentionally
 * omitted because @xingwen/ui uses vanilla CSS class names.
 */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}
