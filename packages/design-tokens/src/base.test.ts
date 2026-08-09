import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./base.css", import.meta.url), "utf8");
const workspaceCss = readFileSync(
  new URL("./workspace.css", import.meta.url),
  "utf8",
);
const normalizedCss = css
  .replace(/\s+/gu, " ")
  .replace(/\(\s+/gu, "(")
  .replace(/\s+\)/gu, ")");
const normalizedWorkspaceCss = workspaceCss
  .replace(/\s+/gu, " ")
  .replace(/\(\s+/gu, "(")
  .replace(/\s+\)/gu, ")");

describe("bluegray raw tokens", () => {
  it("exposes the full bluegray scale on hue 235", () => {
    const expected = [
      "--raw-bluegray-50: oklch(0.975 0.006 235)",
      "--raw-bluegray-100: oklch(0.945 0.008 235)",
      "--raw-bluegray-200: oklch(0.885 0.011 235)",
      "--raw-bluegray-300: oklch(0.805 0.014 235)",
      "--raw-bluegray-400: oklch(0.685 0.016 235)",
      "--raw-bluegray-500: oklch(0.57 0.018 235)",
      "--raw-bluegray-600: oklch(0.47 0.02 235)",
      "--raw-bluegray-700: oklch(0.38 0.022 235)",
      "--raw-bluegray-800: oklch(0.29 0.024 235)",
      "--raw-bluegray-900: oklch(0.21 0.026 235)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("exposes the cold paper scale on hue 230", () => {
    const expected = [
      "--raw-paper-0: oklch(0.995 0.002 230)",
      "--raw-paper-50: oklch(0.978 0.004 230)",
      "--raw-paper-100: oklch(0.955 0.006 230)",
      "--raw-paper-200: oklch(0.925 0.008 230)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("exposes semantic status raw tokens", () => {
    const expected = [
      "--raw-success-500: oklch(0.56 0.07 165)",
      "--raw-warning-500: oklch(0.6 0.075 80)",
      "--raw-error-500: oklch(0.56 0.085 25)",
      "--raw-info-500: oklch(0.57 0.06 245)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });
});

describe("semantic tokens", () => {
  it("maps surface tokens to paper raw", () => {
    const expected = [
      "--color-canvas: var(--raw-paper-50)",
      "--color-surface: var(--raw-paper-0)",
      "--color-surface-muted: var(--raw-paper-100)",
      "--color-surface-hover: var(--raw-paper-200)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("maps ink tokens to bluegray raw", () => {
    const expected = [
      "--color-ink-primary: var(--raw-bluegray-900)",
      "--color-ink-secondary: var(--raw-bluegray-600)",
      "--color-ink-tertiary: var(--raw-bluegray-600)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("maps border tokens to bluegray raw", () => {
    const expected = [
      "--color-border: var(--raw-bluegray-200)",
      "--color-border-strong: var(--raw-bluegray-400)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("maps brand tokens to bluegray raw", () => {
    const expected = [
      "--color-brand: var(--raw-bluegray-500)",
      "--color-brand-hover: var(--raw-bluegray-600)",
      "--color-brand-pressed: var(--raw-bluegray-700)",
      "--color-brand-muted: var(--raw-bluegray-100)",
      "--color-brand-on: var(--raw-paper-0)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("maps focus and status tokens", () => {
    const expected = [
      "--color-focus: var(--raw-bluegray-400)",
      "--color-success: var(--raw-success-500)",
      "--color-warning: var(--raw-warning-500)",
      "--color-error: var(--raw-error-500)",
      "--color-info: var(--raw-info-500)",
      "--color-live: var(--raw-success-500)",
      "--color-cached: var(--raw-warning-500)",
      "--color-revised: var(--raw-info-500)",
      "--color-demo: var(--raw-bluegray-600)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });

  it("maps visual tokens to bluegray raw", () => {
    const expected = [
      "--color-visual-celestial-ink: var(--raw-bluegray-700)",
      "--color-visual-celestial-deep: var(--raw-bluegray-900)",
      "--color-visual-celestial-soft: var(--raw-bluegray-200)",
      "--color-visual-particle: var(--raw-bluegray-500)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }
  });
});

describe("typography and motion tokens", () => {
  it("exposes font family tokens", () => {
    expect(css).toContain("--xw-font-sans:");
    expect(css).toContain("--xw-font-serif:");
    expect(css).toContain("--xw-font-mono:");
  });

  it("exposes the font size scale", () => {
    for (const token of [
      "--font-size-00",
      "--font-size-0",
      "--font-size-1",
      "--font-size-2",
      "--font-size-3",
      "--font-size-4",
      "--font-size-5",
      "--font-size-6",
      "--font-size-7",
      "--font-size-8",
    ]) {
      expect(css).toContain(token);
    }
  });

  it("exposes radius, shadow and motion tokens", () => {
    for (const token of [
      "--radius-xs",
      "--radius-sm",
      "--radius-md",
      "--radius-lg",
      "--radius-pill",
      "--shadow-float",
      "--shadow-modal",
      "--motion-instant",
      "--motion-fast",
      "--motion-base",
      "--motion-slow",
      "--motion-scene",
      "--ease-standard",
      "--ease-enter",
      "--ease-exit",
    ]) {
      expect(css).toContain(token);
    }
  });
});

describe("Core semantic geometry tokens", () => {
  it("keeps Workspace text roles aligned with the OpenHands scale", () => {
    expect(css).toContain("--font-size-ui-label: var(--font-size-0);");
    expect(css).toContain("--font-size-ui-body: 0.875rem;");
    expect(css).toContain("--font-size-ui-heading: 1.25rem;");
    expect(css).toContain("--line-height-ui-label: 1.5;");
    expect(css).toContain("--line-height-ui-body: 1.6;");
    expect(css).toContain("--line-height-ui-heading: 1.5;");
  });

  it("exposes the shared spacing, control and icon scales", () => {
    for (const token of [
      "--space-1",
      "--space-2",
      "--space-3",
      "--space-4",
      "--space-5",
      "--space-6",
      "--space-8",
      "--control-size-xs",
      "--control-size-sm",
      "--control-size-md",
      "--control-size-lg",
      "--icon-size-xs",
      "--icon-size-sm",
      "--icon-size-md",
      "--icon-size-lg",
    ]) {
      expect(css).toContain(token);
    }
  });

  it("keeps control sizes ordered for shared components", () => {
    expect(css).toContain("--control-size-xs: 1.5rem;");
    expect(css).toContain("--control-size-sm: 2rem;");
    expect(css).toContain("--control-size-md: 2.25rem;");
    expect(css).toContain("--control-size-lg: 2.5rem;");
    expect(css).toContain("--border-width-default: 1px;");
  });
});

describe("workspace semantic geometry tokens", () => {
  it("keeps Workspace layout facts out of the Core foundation", () => {
    expect(css).not.toMatch(/--workspace-[a-z0-9-]+\s*:/iu);
    expect(workspaceCss).toMatch(/--workspace-[a-z0-9-]+\s*:/iu);
  });

  it("exposes the Workspace layout, panel, overlay and motion authority", () => {
    for (const token of [
      "--workspace-header-block-size",
      "--workspace-sidebar-expanded-inline-size",
      "--workspace-sidebar-collapsed-inline-size",
      "--workspace-sidebar-inner-inline-size",
      "--workspace-sidebar-icon-slot-inline-size",
      "--workspace-sidebar-row-block-size",
      "--workspace-content-max-inline-size",
      "--workspace-min-inline-size",
      "--workspace-composer-max-block-size",
      "--workspace-composer-input-min-block-size",
      "--workspace-composer-input-max-block-size",
      "--workspace-composer-input-reserved-block-size",
      "--workspace-composer-keyboard-step",
      "--workspace-composer-padding-inline",
      "--workspace-composer-padding-block",
      "--workspace-composer-row-gap",
      "--workspace-composer-actions-reserved-block-size",
      "--workspace-composer-grip-inline-size",
      "--workspace-composer-grip-indicator-inline-size",
      "--workspace-composer-grip-indicator-block-size",
      "--workspace-panel-default-ratio",
      "--workspace-panel-min-ratio",
      "--workspace-panel-max-ratio",
      "--workspace-panel-keyboard-step",
      "--workspace-command-menu-max-inline-size",
      "--workspace-command-menu-max-block-size",
      "--workspace-command-menu-viewport-offset",
      "--workspace-motion-panel",
      "--workspace-ease-panel",
      "--workspace-header-control-reserve-inline",
      "--workspace-layer-sidebar",
      "--workspace-tab-overflow-min-inline-size",
      "--workspace-layer-tab-overflow",
      "--workspace-layer-command-menu",
      "--workspace-layer-panel-drag-shield",
    ]) {
      expect(normalizedWorkspaceCss).toContain(token);
    }
  });

  it("derives Workspace geometry from Core tokens", () => {
    expect(normalizedWorkspaceCss).toContain(
      "--workspace-sidebar-row-block-size: var(--control-size-md)",
    );
    expect(normalizedWorkspaceCss).toContain(
      "--workspace-header-control-reserve-inline: calc(var(--workspace-header-control-inset-inline) + var(--control-size-sm))",
    );
    expect(normalizedWorkspaceCss).toContain(
      "var(--workspace-composer-row-gap) + var(--workspace-composer-actions-reserved-block-size)",
    );
  });
});

describe("palette vocabulary hygiene", () => {
  it("does not contain disallowed haze, lunar or raw-gray tokens", () => {
    expect(css).not.toMatch(/haze|lunar|--raw-gray-/iu);
  });

  it("does not embed bare hex color literals", () => {
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/iu);
  });
});
