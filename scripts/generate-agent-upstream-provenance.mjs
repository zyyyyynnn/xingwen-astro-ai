#!/usr/bin/env node

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";

import {
  computeSelectedTreeSha256,
  listVendoredFiles,
  toPosix,
} from "./agent-upstream-provenance.mjs";
import { isForbiddenVendoredProductPath } from "./agent-upstream-boundary.mjs";
import { analyzeVendoredImportGraph } from "./agent-upstream-graph.mjs";

const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const SOURCE_ROOT = `${UPSTREAM_ROOT}/src`;
const REPOSITORY = "https://github.com/OpenHands/OpenHands.git";
const TAG = "v1.10.0";
const COMMIT = "56638693908b8ac83a2fa3bde6eb6c33aae37f4b";
const LICENSE = "MIT";
const ADOPTED_CLASSIFICATIONS = new Set([
  "REQUIRED_VENDOR",
  "REQUIRED_TRANSITIVE",
  "PARTIAL_SURGICAL",
]);

const MINIMAL_PATCH = new Set([
  "src/components/features/chat/chat-messages-skeleton.tsx",
  "src/components/features/chat/chat-send-button.tsx",
  "src/components/features/chat/chat-stop-button.tsx",
  "src/components/features/chat/components/chat-input-field.tsx",
  "src/components/features/chat/components/chat-input-grip.tsx",
  "src/components/features/chat/components/chat-input-row.tsx",
  "src/components/features/sidebar/sidebar-layout.ts",
  "src/components/ui/resize-handle.tsx",
  "src/hooks/chat/use-grip-resize.ts",
  "src/hooks/use-resizable-panels.ts",
  "src/stores/sidebar-store.ts",
]);
const STRUCTURE_REPLACEMENT = new Set([
  "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx",
  "src/components/features/chat/chat-interface.tsx",
  "src/components/features/chat/components/chat-input-actions.tsx",
  "src/components/features/chat/components/chat-input-container.tsx",
  "src/components/features/chat/custom-chat-input.tsx",
  "src/components/features/chat/error-message-banner.tsx",
  "src/components/features/chat/interactive-chat-box.tsx",
  "src/components/features/command-menu/command-menu-items.tsx",
  "src/components/features/command-menu/command-menu-trigger.tsx",
  "src/components/features/command-menu/command-menu.tsx",
  "src/components/features/conversation/conversation-tabs/conversation-tabs.tsx",
  "src/components/features/conversation/conversation-main/conversation-main.tsx",
  "src/components/features/sidebar/sidebar-rail-body.tsx",
  "src/components/features/sidebar/sidebar.tsx",
  "src/root.tsx",
  "src/routes/conversation.tsx",
  "src/routes/root-layout.tsx",
  "src/utils/utils.ts",
]);
function adoptionClass(upstreamPath) {
  if (MINIMAL_PATCH.has(upstreamPath)) return "KEEP_WITH_MINIMAL_PATCH";
  if (STRUCTURE_REPLACEMENT.has(upstreamPath)) {
    return "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT";
  }
  return "KEEP_AS_IS";
}

function modificationReason(upstreamPath) {
  if (upstreamPath.includes("/command-menu/")) {
    return "Removed upstream routes and localization coupling while retaining searchable overlay, shortcut, keyboard selection, and focus mechanics.";
  }
  if (
    upstreamPath.includes("/sidebar/") ||
    upstreamPath.endsWith("sidebar-store.ts")
  ) {
    return "Removed coding, cloud, and mobile navigation while retaining the desktop rail and collapse mechanics.";
  }
  if (
    upstreamPath.includes("/chat/") ||
    upstreamPath.includes("chat-interface")
  ) {
    return "Removed coding and backend-domain coupling while retaining composer, execution state, cancel, retry, error, disclosure, scroll, and resize mechanics.";
  }
  if (
    upstreamPath.includes("conversation-tabs") ||
    upstreamPath.includes("resize-handle") ||
    upstreamPath.includes("resizable-panels")
  ) {
    return "Removed coding panel content while retaining tabs, split-panel sizing, and keyboard mechanics.";
  }
  if (upstreamPath.includes("conversation-main")) {
    return "Removed mobile and coding panel content while retaining ConversationMain split-panel, resize, visibility, header, and panel-frame mechanics.";
  }
  if (upstreamPath === "src/utils/utils.ts") {
    return "Reduced the utility surface to class composition used by the adopted import graph.";
  }
  return "Removed upstream routing, backend, coding, cloud, and mobile dependencies while retaining the Agent workspace product structure.";
}

function writeJson(root, relativePath, value) {
  writeFileSync(
    resolve(root, relativePath),
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

export function generateAgentUpstreamProvenance(root = process.cwd()) {
  const sourceDirectory = resolve(root, SOURCE_ROOT);
  if (!existsSync(sourceDirectory)) {
    throw new Error(`Missing vendored source root: ${SOURCE_ROOT}`);
  }

  const scope = JSON.parse(
    readFileSync(resolve(root, `${UPSTREAM_ROOT}/source-scope.json`), "utf8"),
  );
  const lock = JSON.parse(
    readFileSync(resolve(root, `${UPSTREAM_ROOT}/upstream-lock.json`), "utf8"),
  );
  const scopeByPath = new Map(
    scope.files.map((entry) => [entry.upstream_path, entry]),
  );
  const diskFiles = listVendoredFiles(sourceDirectory);

  const entries = diskFiles.map((absolutePath) => {
    const localPath = toPosix(relative(root, absolutePath));
    const upstreamPath = `src/${toPosix(relative(sourceDirectory, absolutePath))}`;
    if (isForbiddenVendoredProductPath(upstreamPath)) {
      throw new Error(
        `Vendored path crosses the desktop product boundary: ${upstreamPath}`,
      );
    }
    const scopeEntry = scopeByPath.get(upstreamPath);
    if (
      !scopeEntry ||
      !ADOPTED_CLASSIFICATIONS.has(scopeEntry.classification)
    ) {
      throw new Error(
        `Vendored path is outside the adopted scope: ${upstreamPath}`,
      );
    }

    const entryAdoptionClass = adoptionClass(upstreamPath);
    const modified = entryAdoptionClass !== "KEEP_AS_IS";
    return {
      upstream_path: upstreamPath,
      local_path: localPath,
      adoption_class: entryAdoptionClass,
      modified,
      modification_reason: modified ? modificationReason(upstreamPath) : null,
    };
  });

  const importGraph = analyzeVendoredImportGraph({
    root,
    sourceRoot: SOURCE_ROOT,
    diskPaths: new Set(entries.map((entry) => entry.local_path)),
  });
  if (importGraph.unresolved.length > 0) {
    throw new Error(
      `Vendored source has unresolved local imports: ${importGraph.unresolved
        .map(({ from, specifier }) => `${from} -> ${specifier}`)
        .join(", ")}.`,
    );
  }
  if (importGraph.unreachable.length > 0) {
    throw new Error(
      `Vendored source is outside the src/root.tsx dependency closure: ${importGraph.unreachable.join(", ")}.`,
    );
  }

  const keepAsIsPaths = entries
    .filter((entry) => entry.adoption_class === "KEEP_AS_IS")
    .map((entry) => entry.upstream_path.slice("src/".length));
  const actualKeepAsIsDigest = computeSelectedTreeSha256(
    sourceDirectory,
    keepAsIsPaths,
  );
  if (actualKeepAsIsDigest !== lock.keep_as_is_tree_sha256) {
    throw new Error(
      "KEEP_AS_IS source differs from the aggregate digest frozen in upstream-lock.json.",
    );
  }

  writeJson(root, `${UPSTREAM_ROOT}/provenance.json`, {
    schema: "xingwen.agent-upstream.provenance/v2",
    generated_by: "scripts/generate-agent-upstream-provenance.mjs",
    source: {
      repository: REPOSITORY,
      tag: TAG,
      commit: COMMIT,
      license: LICENSE,
    },
    keep_as_is_tree_sha256: lock.keep_as_is_tree_sha256,
    entries,
  });

  return { vendored: entries.length };
}

if (import.meta.main) {
  const result = generateAgentUpstreamProvenance();
  console.log(
    `Generated OpenHands provenance for ${result.vendored} vendored files with one frozen KEEP_AS_IS aggregate digest.`,
  );
}
