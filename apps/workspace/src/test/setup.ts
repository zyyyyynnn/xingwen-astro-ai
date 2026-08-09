import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { vi } from "vitest";

const workspaceCss = readFileSync(
  resolve(process.cwd(), "../../packages/design-tokens/src/workspace.css"),
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
