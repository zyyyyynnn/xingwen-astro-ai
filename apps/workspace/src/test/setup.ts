import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { vi } from "vitest";

const nodeRequire = createRequire(import.meta.url);
const workspaceCss = readFileSync(
  nodeRequire.resolve("@xingwen/design-tokens/workspace.css"),
  "utf8",
);

function readUnitlessWorkspaceToken(name: string) {
  const match = workspaceCss.match(new RegExp(`${name}\\s*:\\s*([^;]+);`, "u"));
  const value = match?.[1]?.trim();
  if (!value || !/^\d+(?:\.\d+)?$/u.test(value)) {
    throw new Error(`Workspace test token ${name} is missing or invalid.`);
  }
  return value;
}

for (const [workspaceName, openHandsName] of [
  ["--workspace-panel-default-ratio", "--oh-panel-default-ratio"],
  ["--workspace-panel-min-ratio", "--oh-panel-min-ratio"],
  ["--workspace-panel-max-ratio", "--oh-panel-max-ratio"],
  ["--workspace-panel-keyboard-step", "--oh-panel-keyboard-step"],
] as const) {
  document.documentElement.style.setProperty(
    openHandsName,
    readUnitlessWorkspaceToken(workspaceName),
  );
}

Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(Element.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  value: vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  })),
});

class ObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal("IntersectionObserver", ObserverStub);
vi.stubGlobal("ResizeObserver", ObserverStub);
