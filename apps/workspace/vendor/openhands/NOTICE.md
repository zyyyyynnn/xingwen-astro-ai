# NOTICE — OpenHands Vendored Source

This directory (`apps/workspace/vendor/openhands/`) contains **metadata only**
at the A-21 Phase 2 stage. Actual production TypeScript/TSX source is vendored
in a later task (#174 / A-22) strictly from the frozen upstream ref below.

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

When A-22 vendors OpenHands source files into `apps/workspace/vendor/openhands/src/`,
each file MUST retain its MIT attribution and be recorded in the provenance
manifest (`provenance-schema.json`) with its upstream path, 40-char SHA, and
adoption class.

## Excluded scope (never vendored)

Coding / IDE / Cloud / Enterprise surfaces are excluded from adoption:
Terminal (xterm), DiffViewer (Monaco), Browser panel, Git diff/status UI,
VSCode link, `api/git-service`, `api/cloud`, Electron desktop shell. These are
out of scope for the Xingwen Research Workspace and must not enter production
import graphs.

## Single upstream rule

OpenHands is the **unique** Agent Product source. No source from AnythingLLM,
LibreChat, or Dify — nor any hand-written reimplementation of Shell /
Navigation / Activity / Composer / Panel mechanics — may supplement it.
Product mechanics are preserved from OpenHands; only the research domain
(Renderers / Adapter / ViewModel) is added by Xingwen.
