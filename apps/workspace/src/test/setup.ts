import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

for (const [name, value] of [
  ["--oh-panel-default-ratio", "58"],
  ["--oh-panel-min-ratio", "38"],
  ["--oh-panel-max-ratio", "72"],
  ["--oh-panel-keyboard-step", "2"],
] as const) {
  document.documentElement.style.setProperty(name, value);
}

Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: vi.fn(),
});
