# NOTICE — OpenHands Vendored Source

This directory is the authoritative OpenHands upstream root. Adoption metadata
is stored at the root; vendored source, when present, is stored under `src/`.

## Upstream source of truth

- **Product**: OpenHands
- **Repository**: https://github.com/OpenHands/OpenHands.git
- **Tag**: v1.10.0
- **Commit**: `56638693908b8ac83a2fa3bde6eb6c33aae37f4b` (40-char SHA)
- **License**: MIT

## Attribution

OpenHands is licensed under the MIT License. The original `LICENSE` text is
preserved in `LICENSE.upstream` in this directory and must accompany any
vendored source copied from the frozen ref.

```
The MIT License (MIT)
Copyright © 2025 OpenHands contributors
```

When OpenHands source files are vendored into
`apps/workspace/upstream/openhands/src/`, each file MUST retain its MIT
attribution and be recorded in the provenance manifest (`provenance.json`)
with its upstream path, local path, adoption class, and modification intent.
The manifest binds all unmodified source files once to the frozen repository,
tag, 40-character commit, and one aggregate digest. Adapted files remain
reviewable through their recorded upstream path, adoption class, and reason.
Semantic/privacy constraints in `source-policy.json` are mandatory for every
vendored file. The vendored tree is the exact resolved local-import closure of
`src/root.tsx`; dormant facades and files with unresolved local imports are not
retained.

## Excluded scope

Frontend API and Agent Runtime integration, authentication, WebSocket,
Telemetry, compatibility modules, mobile-only navigation, and Coding / IDE /
Cloud / Enterprise surfaces are excluded from adoption. This includes
Terminal, DiffViewer, Browser and repository panels, Git controls, VSCode,
Sandbox, deployment preview, and Electron desktop-shell integration.

Model-private reasoning is also outside the Xingwen product boundary. Raw
`thought`, `reasoning_content`, `thinking_blocks`, inline `<think>` content,
and equivalent private-reasoning paths must not be rendered, persisted, or
transported as product content. OpenHands disclosure mechanics may be retained
only after the semantic surgery required by `source-policy.json`, and may only
receive explicit public/auditable reasoning.

## Single upstream rule

OpenHands is the **unique** Agent Product source. No source from any other
Agent product, nor any hand-written reimplementation of Shell / Navigation /
Activity / Composer / Panel mechanics, may supplement it. Product mechanics are
preserved from OpenHands. Research-domain Renderers, Adapter, and ViewModel
work is not included in this source adoption.
