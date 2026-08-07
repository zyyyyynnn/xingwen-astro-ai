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
with its upstream path, 40-char SHA, and adoption class.

## Excluded scope (never vendored)

Coding / IDE / Cloud / Enterprise surfaces are excluded from adoption:
Terminal (xterm), DiffViewer (Monaco), Browser panel, Git diff/status UI,
VSCode link, `api/git-service`, `api/cloud`, Electron desktop shell. These are
out of scope for the Xingwen Research Workspace and must not enter production
import graphs.

## Single upstream rule

OpenHands is the **unique** Agent Product source. No source from any other
Agent product, nor any hand-written reimplementation of Shell / Navigation /
Activity / Composer / Panel mechanics, may supplement it. Product mechanics are
preserved from OpenHands; only the research domain (Renderers / Adapter /
ViewModel) is added by Xingwen.
