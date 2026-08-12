#!/usr/bin/env node

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";

import {
  computeSelectedTreeSha256,
  listVendoredFiles,
  toPosix,
} from "./agent-upstream-provenance.mjs";
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
  "src/components/features/sidebar/sidebar-layout.ts",
  "src/components/ui/resize-handle.tsx",
  "src/hooks/use-resizable-panels.ts",
  "src/stores/sidebar-store.ts",
]);
const STRUCTURE_REPLACEMENT = new Set([
  "src/components/conversation-events/chat/event-message-components/event-group.tsx",
  "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx",
  "src/components/conversation-events/chat/event-message.tsx",
  "src/components/conversation-events/chat/group-events.ts",
  "src/components/conversation-events/chat/messages.tsx",
  "src/components/features/chat/chat-message.tsx",
  "src/components/features/chat/user-message-body.tsx",
  "src/components/features/chat/chat-send-button.tsx",
  "src/components/features/chat/components/chat-input-actions.tsx",
  "src/components/features/chat/components/chat-input-container.tsx",
  "src/components/features/chat/components/chat-input-field.tsx",
  "src/components/features/chat/components/chat-input-grip.tsx",
  "src/components/features/chat/components/chat-input-row.tsx",
  "src/components/features/chat/custom-chat-input.tsx",
  "src/components/features/chat/chat-interface.tsx",
  "src/components/features/chat/interactive-chat-box.tsx",
  "src/components/shared/buttons/scroll-to-bottom-button.tsx",
  "src/components/features/command-menu/command-menu-items.tsx",
  "src/components/features/command-menu/command-menu-trigger.tsx",
  "src/components/features/command-menu/command-menu.tsx",
  "src/components/features/conversation/conversation-main/chat-interface-wrapper.tsx",
  "src/components/features/conversation/conversation-main/conversation-main.tsx",
  "src/components/features/conversation/conversation-name-with-status.tsx",
  "src/components/features/sidebar/sidebar-rail-body.tsx",
  "src/components/features/sidebar/sidebar.tsx",
  "src/root.tsx",
  "src/routes/conversation.tsx",
  "src/routes/root-layout.tsx",
  "src/hooks/chat/use-grip-resize.ts",
  "src/hooks/use-scroll-to-bottom.ts",
  "src/utils/utils.ts",
]);
function adoptionClass(upstreamPath) {
  if (MINIMAL_PATCH.has(upstreamPath)) return "KEEP_WITH_MINIMAL_PATCH";
  if (STRUCTURE_REPLACEMENT.has(upstreamPath)) {
    return "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT";
  }
  return "KEEP_AS_IS";
}

const MODIFICATION_REASONS = new Map([
  [
    "src/components/conversation-events/chat/event-message-components/event-group.tsx",
    "Kept the OpenHands collapsible action-run group while accepting only public research presentation events.",
  ],
  [
    "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx",
    "Kept the public disclosure interaction while restricting content to an auditable caller-provided value.",
  ],
  [
    "src/components/features/chat/chat-interface.tsx",
    "Kept the OpenHands scroll stream, empty and started composition, tail following, Composer placement, and error slot while injecting the research runtime seam.",
  ],
  [
    "src/components/conversation-events/chat/event-message.tsx",
    "Kept the OpenHands generic event disclosure and status hierarchy over public research events.",
  ],
  [
    "src/components/conversation-events/chat/group-events.ts",
    "Kept the OpenHands consecutive action grouping algorithm over the public research event contract.",
  ],
  [
    "src/components/conversation-events/chat/messages.tsx",
    "Kept the OpenHands ordered Messages composition and finalized action-group behavior.",
  ],
  [
    "src/components/features/chat/chat-message.tsx",
    "Kept OpenHands user and agent message geometry while removing runtime-only markdown, media, copy, and branch dependencies.",
  ],
  [
    "src/components/features/chat/user-message-body.tsx",
    "Kept the OpenHands long-user-message measurement, collapse, fade, and explicit expansion mechanic over public research text.",
  ],
  [
    "src/components/features/chat/chat-send-button.tsx",
    "Kept the OpenHands submit and pending button behavior with shared Xingwen icons.",
  ],
  [
    "src/components/features/chat/components/chat-input-actions.tsx",
    "Kept the OpenHands Composer action-row and submit ownership while injecting research-domain leading actions.",
  ],
  [
    "src/components/features/chat/components/chat-input-container.tsx",
    "Kept the OpenHands single Composer container and focus boundary while removing coding attachments and mode controls.",
  ],
  [
    "src/components/features/chat/components/chat-input-field.tsx",
    "Kept the OpenHands contenteditable input behavior with controlled research copy.",
  ],
  [
    "src/components/features/chat/components/chat-input-grip.tsx",
    "Kept the OpenHands pointer and keyboard Composer resize grip.",
  ],
  [
    "src/components/features/chat/components/chat-input-row.tsx",
    "Kept the OpenHands Composer input-row geometry without coding-only controls.",
  ],
  [
    "src/components/features/chat/custom-chat-input.tsx",
    "Kept the OpenHands contenteditable, paste, submit, controlled-value, and resize orchestration over the research submit adapter.",
  ],
  [
    "src/components/features/chat/interactive-chat-box.tsx",
    "Kept the OpenHands InteractiveChatBox boundary while injecting controlled research Composer state.",
  ],
  [
    "src/components/shared/buttons/scroll-to-bottom-button.tsx",
    "Kept the OpenHands return-to-latest control with shared Xingwen icons and research-language accessibility copy.",
  ],
  [
    "src/components/features/command-menu/command-menu-items.tsx",
    "Kept searchable command item rendering while limiting definitions to current Workspace capabilities.",
  ],
  [
    "src/components/features/command-menu/command-menu-trigger.tsx",
    "Kept command-menu trigger keyboard and focus behavior with the Workspace label and shortcut.",
  ],
  [
    "src/components/features/command-menu/command-menu.tsx",
    "Kept portal, combobox, filtering, active-option scroll, keyboard selection, and focus return mechanics.",
  ],
  [
    "src/components/features/conversation/conversation-main/chat-interface-wrapper.tsx",
    "Kept the centered conversation frame and public Thread panel ownership while injecting the thin runtime seam.",
  ],
  [
    "src/components/features/conversation/conversation-main/conversation-main.tsx",
    "Kept ConversationMain split-panel, resize, visibility, header, and panel-frame mechanics while composing public surfaces through the shared shadcn ScrollArea.",
  ],
  [
    "src/components/features/conversation/conversation-name-with-status.tsx",
    "Kept title/status header alignment while replacing conversation identity with the Workspace label.",
  ],
  [
    "src/components/features/sidebar/sidebar-layout.ts",
    "Kept desktop rail width and clipping geometry while removing mobile and coding navigation branches.",
  ],
  [
    "src/components/features/sidebar/sidebar-rail-body.tsx",
    "Kept rail collapse controls, stable inner geometry, and task-list composition with Xingwen labels.",
  ],
  [
    "src/components/features/sidebar/sidebar.tsx",
    "Kept desktop sidebar state, toggle anchoring, and keyboard activation for the Workspace shell.",
  ],
  [
    "src/components/ui/resize-handle.tsx",
    "Kept split-panel pointer and keyboard resizing with a stable separator and motion-safe transitions.",
  ],
  [
    "src/hooks/use-resizable-panels.ts",
    "Kept split-panel percentage sizing, persistence, pointer drag, and keyboard adjustment mechanics.",
  ],
  [
    "src/hooks/chat/use-grip-resize.ts",
    "Kept the OpenHands Composer height, pointer, keyboard, and content-resize mechanics.",
  ],
  [
    "src/hooks/use-scroll-to-bottom.ts",
    "Kept the OpenHands manual-scroll-aware tail-following state and explicit resume behavior.",
  ],
  [
    "src/root.tsx",
    "Kept the OpenHands root composition while exposing only the thin runtime and public Research Thread/Inspector seams.",
  ],
  [
    "src/routes/conversation.tsx",
    "Kept the upstream conversation route boundary as a direct ConversationMain composition.",
  ],
  [
    "src/routes/root-layout.tsx",
    "Kept the single Workspace layout composition for desktop navigation, conversation, and command overlay.",
  ],
  [
    "src/stores/sidebar-store.ts",
    "Kept persistent sidebar collapse state and the desktop rail ownership boundary.",
  ],
  [
    "src/utils/utils.ts",
    "Kept only the class-composition utility required by the adopted Workspace import graph.",
  ],
]);

function modificationReason(upstreamPath) {
  const reason = MODIFICATION_REASONS.get(upstreamPath);
  if (!reason) {
    throw new Error(
      `Missing modification reason for adapted source: ${upstreamPath}`,
    );
  }
  return reason;
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
  const approvedMechanicsPaths = new Set(
    (scope.approved_mechanics ?? []).flatMap(
      (surface) => surface.upstream_paths ?? [],
    ),
  );
  const transitiveMechanicsPaths = new Set(
    (scope.transitive_mechanics ?? []).flatMap(
      (surface) => surface.upstream_paths ?? [],
    ),
  );
  const adoptedMechanicsPaths = new Set([
    ...approvedMechanicsPaths,
    ...transitiveMechanicsPaths,
  ]);
  if (approvedMechanicsPaths.size === 0) {
    throw new Error("Approved mechanics scope is empty.");
  }
  const diskFiles = listVendoredFiles(sourceDirectory);
  const diskUpstreamPaths = new Set(
    diskFiles.map(
      (absolutePath) =>
        `src/${toPosix(relative(sourceDirectory, absolutePath))}`,
    ),
  );
  for (const upstreamPath of adoptedMechanicsPaths) {
    if (!diskUpstreamPaths.has(upstreamPath)) {
      throw new Error(
        `Approved mechanics path is not vendored: ${upstreamPath}`,
      );
    }
  }

  const entries = diskFiles.map((absolutePath) => {
    const localPath = toPosix(relative(root, absolutePath));
    const upstreamPath = `src/${toPosix(relative(sourceDirectory, absolutePath))}`;
    const scopeEntry = scopeByPath.get(upstreamPath);
    if (!adoptedMechanicsPaths.has(upstreamPath)) {
      throw new Error(
        `Vendored path is outside the approved or transitive mechanics scope: ${upstreamPath}`,
      );
    }
    if (
      !scopeEntry ||
      !ADOPTED_CLASSIFICATIONS.has(scopeEntry.classification)
    ) {
      throw new Error(
        `Adopted mechanics path is not classified as adopted: ${upstreamPath}`,
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
