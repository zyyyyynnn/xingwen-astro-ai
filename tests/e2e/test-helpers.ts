import type { Locator, Page } from "@playwright/test";

export type BoundingBox = NonNullable<
  Awaited<ReturnType<Locator["boundingBox"]>>
>;

export async function requireBoundingBox(
  locator: Locator,
  label: string,
): Promise<BoundingBox> {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`${label} has no visible bounding box`);
  return box;
}

export function requireValue<T>(value: T | null | undefined, label: string): T {
  if (value == null) throw new Error(`${label} is unavailable`);
  return value;
}

export function requireViewport(page: Page) {
  return requireValue(page.viewportSize(), "viewport");
}
