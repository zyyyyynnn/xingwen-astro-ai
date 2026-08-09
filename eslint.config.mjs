import { readFileSync } from "node:fs";

import eslint from "@eslint/js";
import astro from "eslint-plugin-astro";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const agentUpstreamProvenance = JSON.parse(
  readFileSync(
    new URL(
      "./apps/workspace/upstream/openhands/provenance.json",
      import.meta.url,
    ),
    "utf8",
  ),
);
const unmodifiedAgentUpstreamFiles = agentUpstreamProvenance.entries
  .filter((entry) => entry.modified === false)
  .map((entry) => entry.local_path);

export default tseslint.config(
  {
    ignores: [
      "**/dist/**",
      "**/node_modules/**",
      ".codegraph/**",
      ".turbo/**",
      "packages/schemas/generated/**",
      "packages/contracts/src/generated/**",
      ...unmodifiedAgentUpstreamFiles,
    ],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: reactHooks.configs.flat.recommended.rules,
  },
  {
    files: ["apps/workspace/**/*.{ts,tsx}", "tests/e2e/**/*.ts"],
    rules: {
      "@typescript-eslint/no-non-null-assertion": "error",
    },
  },
);
