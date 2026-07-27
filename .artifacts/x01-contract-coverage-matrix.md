# X-01 Contract Coverage Matrix (M1 required set)

Baseline HEAD: `9f3380f9e4d14fd34a27db7632060fe13db24487` (= origin/main at #131 start; previous
closure baseline was `e36a95e2c59e5e2a319a7c816d64ff44692c53ba`)

Authoritative Contract = contract-only OpenAPI in `apps/api/src/app/contracts/v2.py`
(`create_v2_contract_app`, **27 operationIds** after #131, asserted exactly by
`apps/api/tests/test_v2_core_contract.py::test_openapi_31_has_stable_unique_operation_ids_and_transport_primitives`).

## #131 frozen additions (decided before implementation)

Only three operations are added; the existing 24 authoritative operationIds,
methods and paths are preserved verbatim. Frozen targets:

| opId | method+path | required headers | request schema | success response |
|---|---|---|---|---|
| listResearchProjects | GET /api/v2/projects (`cursor`, `limit` query) | — | — | 200 CollectionEnvelope[ResearchProject] |
| createResearchProject | POST /api/v2/projects | Idempotency-Key | CreateResearchProjectRequest (name, description="", case_key) | 201 Envelope[ResearchProject] |
| createResearchContractDraft | POST /api/v2/projects/{project_id}/contract-drafts | Idempotency-Key | CreateResearchContractDraftRequest (intent, contract) | 201 Envelope[ResearchContractDraft] |

Conventions reused (not invented): `Idempotency-Key` + persisted
`idempotency_key`/`request_hash` replay-or-409 exactly like
`confirmResearchContract`/`createResearchRun`; nested creation path naming
follows `POST /projects/{id}/contracts` ↔ `/research-contracts/{id}`
(`contract-drafts` ↔ `/research-contract-drafts/{id}`); cursor pagination and
hidden-404 ownership semantics follow the existing collection and read
operations. `execution_mode` remains Run-only and is absent from Project and
Draft payloads.

Legend for **State**:
- `Implemented` — real runtime endpoint mounted + tested against authoritative source (PostgreSQL where applicable).
- `Partial` — exists but has a concrete defect (wrong path/header/DTO/validation), or backend done but frontend/consumer not wired.
- `Missing` — no runtime router / application service at all.

Column meanings: opId | method+path | Pydantic authoring | in generated OpenAPI | in generated TS DTO | runtime Router (mounted?) | Application Service | Persistence/Workflow | HTTP Adapter method | Fixture method | React consumer | test evidence | State.

---

## 1. Session

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| createAnonymousSession | POST /api/v2/sessions | SessionCreated | yes | (session shape, not v2-core) | `sessions.py` mounted | SessionService | InMemorySessionStore | `session.ts ensureSession` ✓ | n/a | composition root | test_v2_security ✓, test_x01_integration_postgres ✓ | **Implemented** |
| getAnonymousSession | GET /api/v2/sessions/current | ResearchSession | yes | — | `sessions.py` mounted | SessionService | InMem | `session.getCurrent` ✓ | n/a | composition root | test_v2_security ✓, test_x01_integration_postgres ✓ | **Implemented** |
| revokeAnonymousSession | DELETE /api/v2/sessions/current | — | yes | — | `sessions.py` mounted | SessionService | InMem | `session.revokeSession` → DELETE /api/v2/sessions/current ✓ | n/a | composition root | test_v2_security ✓, test_x01_integration_postgres ✓ | **Implemented** |

## 2. Project

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| listResearchProjects | GET /api/v2/projects (cursor,limit) | ResearchProject (coll) | yes | yes | `research.py` mounted (#131) | ResearchApplicationService.list_projects ✓ | ResearchProjectModel (PG, keyset cursor) | `projects.list` ✓ | `list` ✓ | entry page | test_v2_research_runtime_postgres::test_list_projects_is_session_scoped_with_stable_cursor ✓ | **Implemented** |
| createResearchProject | POST /api/v2/projects (Idempotency-Key) | CreateResearchProjectRequest → ResearchProject | yes | yes | `research.py` mounted (#131) | ResearchApplicationService.create_project ✓ | ResearchProjectModel (PG, idempotency_key/request_hash) | `projects.create` → Idempotency-Key ✓ | `create` ✓ | entry page | test_public_authoring_chain_creates_project_and_draft ✓ | **Implemented** |
| getResearchProject | GET /api/v2/projects/{project_id} | ResearchProject | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | ResearchProjectModel (PG) | `projects.getById` ✓ | `getById` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |

## 3. Contract Draft

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| createResearchContractDraft | POST /api/v2/projects/{project_id}/contract-drafts (Idempotency-Key) | CreateResearchContractDraftRequest → ResearchContractDraft | yes | yes | `research.py` mounted (#131) | ResearchApplicationService.create_draft ✓ | ResearchContractDraftModel (PG, idempotency_key/request_hash) | `contracts.createDraft` → Idempotency-Key ✓ | `createDraft` ✓ | entry page | test_public_authoring_chain_creates_project_and_draft, test_create_draft_hides_missing_and_cross_session_projects ✓ | **Implemented** |
| getResearchContractDraft | GET /api/v2/research-contract-drafts/{draft_id} | ResearchContractDraft | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | ResearchContractDraftModel (PG, #121) | `contracts.getDraftById` ✓ | `getDraftById` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |
| updateResearchContractDraft | PATCH /api/v2/research-contract-drafts/{draft_id} (If-Match) | UpdateResearchContractDraftRequest | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | ResearchContractDraftModel (PG) | `contracts.saveDraft` → If-Match header ✓ | `saveDraft` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |

## 4. Contract

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| getResearchContract | GET /api/v2/research-contracts/{contract_id} | ResearchContract | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | ResearchContractModel (PG) | `contracts.getContractById` → GET /api/v2/research-contracts/{id} ✓ | ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |
| confirmResearchContract | POST /api/v2/projects/{project_id}/contracts (Idempotency-Key) | ConfirmResearchContractRequest → ResearchContract | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | ResearchContractModel (PG, stores full frozen content) | `contracts.confirm` → Idempotency-Key header ✓ | `confirm` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |

## 5. Run + Events

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| getResearchRun | GET /api/v2/runs/{run_id} | ResearchRun | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | PersistentWorkflowStore.load_snapshot ✓ | `runs.getById` ✓ | ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |
| createResearchRun | POST /api/v2/projects/{project_id}/runs (Idempotency-Key) | CreateRunRequest → ResearchRun | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | PersistentWorkflowStore.create_run ✓ | `runs.save` → Idempotency-Key header ✓ | `save` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |
| listRunEvents | GET /api/v2/runs/{run_id}/events | RunEvent (collection) | yes | yes | `research.py` mounted (#121) | ResearchApplicationService ✓ | store snapshot carries events + latest_event_sequence | `runs.getEvents/listEventsPage/recoverEventsFromSnapshot` (recovery capped to sequence <= latest_event_sequence ✓) | `getEvents` ✓ | workspace shell | test_x01_integration_postgres ✓ | **Implemented** |
| — (list runs) | — | — | **not in contract** | — | — | — | — | n/a (no contract op) | `listByProject` ✓ | — | — | n/a — no contract op |

## 6. Artifact / Evidence reads (MOUNTED, PostgreSQL-backed)

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| listRunArtifacts | GET /api/v2/runs/{run_id}/artifacts | ResearchArtifact (coll) | yes | yes | `artifacts.py` mounted | ArtifactReadService ✓ | ResearchArtifactModel (PG) | `artifacts.listByRun` ✓ | `listByRun` ✓ | workspace shell | test_artifact_reads_postgres ✓, test_x01_integration_postgres ✓ | **Implemented** |
| getResearchArtifact | GET /api/v2/artifacts/{artifact_id} | ResearchArtifactDetail | yes | yes | `artifacts.py` mounted | ArtifactReadService | PG | `getArtifactById` ✓ (validates correct DTO) | ✓ | workspace shell | postgres + consistency(MSW) | **Implemented** |
| getArtifactVersion | GET /api/v2/artifact-versions/{version_id} | ArtifactVersionDetail | yes | yes | `artifacts.py` mounted | ArtifactReadService | PG | `getVersionById` ✓ (validates correct DTO) | ✓ | workspace shell | postgres + consistency | **Implemented** |
| getEvidence | GET /api/v2/evidence/{evidence_id} | EvidenceRead | yes | yes | `artifacts.py` mounted | ArtifactReadService | EvidenceModel (PG) | `evidence.getById` ✓ (enabled, no longer throws) | `getById` ✓ | workspace shell | postgres, test_x01_integration_postgres ✓ | **Implemented** |
| getSourceSnapshot | GET /api/v2/source-snapshots/{snapshot_id} | SourceSnapshotDetail | yes | yes | `artifacts.py` mounted | ArtifactReadService | PG | (none — out of minimal M1 UI scope) | (none) | none | postgres | **Implemented** (backend; out of minimal M1 UI scope) |
| getPaperCollection | GET /api/v2/artifact-versions/{id}/paper-collection | PaperCollectionRead | yes | yes | `artifacts.py` mounted | PaperCollectionReadService | PG | (none — out of minimal M1 UI scope) | (none) | none | test_paper_collection_api | **Implemented** (backend; out of minimal M1 UI scope) |
| listPaperCollectionCandidates | GET .../paper-candidates | PaperCollectionCandidateRead | yes | yes | `artifacts.py` mounted | PaperCollectionReadService | PG | (none — out of minimal M1 UI scope) | (none) | none | test_paper_collection_api | **Implemented** (backend; out of minimal M1 UI scope) |

## 7. Workspace Snapshot

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| getWorkspaceSnapshot | GET /api/v2/projects/{project_id}/workspace-snapshot | WorkspaceSnapshot | yes | yes (generated DTO) | `snapshots.py` mounted (#121) | SnapshotService ✓ | InMemorySnapshotStore | `workspaces.getByProjectId` ✓ | ✓ | workspace shell | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |
| putWorkspaceSnapshot | PUT .../workspace-snapshot (If-Match int, X-CSRF-Token) | WorkspaceSnapshotInput → WorkspaceSnapshot | yes | — | `snapshots.py` mounted (#121) | SnapshotService | InMem | `workspaces.save` → If-Match as integer string ✓ | `save` ✓ | workspace shell | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |

## 8. Share

| opId | method+path | Pydantic | OpenAPI | TS DTO | Runtime Router | App Service | Persistence | HTTP Adapter | Fixture | React consumer | Tests | State |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| listShareSnapshots | GET /api/v2/projects/{project_id}/shares | ShareSnapshot (coll) | yes | yes (generated DTO) | `snapshots.py` mounted (#121) | SnapshotService ✓ | InMemorySnapshotStore | `shares.listByProject` ✓ | ✓ | workspace shell | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |
| createShareSnapshot | POST .../shares (X-CSRF-Token) | CreateShareSnapshotRequest → ShareSnapshotCreated | yes | yes | `snapshots.py` mounted (#121) | SnapshotService | InMem | `shares.create` ✓ (DTO→Domain mapper applied) | ✓ | workspace shell | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |
| revokeShareSnapshot | DELETE .../shares/{share_id} (X-CSRF-Token) | — | yes | — | `snapshots.py` mounted (#121) | SnapshotService | InMem | `shares.revoke` ✓ | ✓ | workspace shell | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |
| getPublicShareSnapshot | GET /api/v2/shares/{share_token} | PublicShareSnapshot | yes | yes | `snapshots.py` mounted (#121) | SnapshotService | InMem | `shares.getPublic` ✓ (correct path, mapper applied) | ✓ (fixture returns projection) | /share/$shareToken view | test_v2_snapshots, test_x01_integration_postgres ✓ | **Implemented** (persistence InMemory — see gaps) |
| — (public share sub-resources: artifact/version/evidence) | — | — | **not in contract** | — | — | — | — | n/a | n/a | n/a | n/a | **Not in contract, not implemented.** The public share response (`PublicShareSnapshot`) embeds redacted `artifact_versions` and `evidence` arrays directly — there are no separate sub-resource endpoints. See note below. |
| — (private single-share read) | — | — | **not in contract** | — | — | — | — | n/a | n/a | n/a | n/a | **Not in contract, not implemented.** No `GET /shares/{share_id}` private read endpoint exists. |

---

## Note on public Share sub-resource endpoints

The #31 closing comment's parity matrix listed four public share operations:
`get_public_share`, `get_public_share_artifact`, `get_public_share_version`,
`get_public_share_evidence`. The backend code at HEAD `e36a95e` contains **only**
`getPublicShareSnapshot` (`GET /api/v2/shares/{share_token}`), which returns a
`PublicShareSnapshot` envelope with embedded `artifact_versions` and `evidence`
arrays. There are no separate sub-resource endpoints for reading individual
artifacts, versions, or evidence within a share. The four-operation listing in the
closing comment was a口径 simplification; the authoritative operationId set is the
24 operationIds asserted by `test_v2_core_contract.py`, and this matrix reflects
that set.

## Note on #31 closing comment operationId naming

The #31 closing comment's parity matrix used snake_case operationId names
(e.g. `create_session`, `get_project`, `get_contract_draft`) and paths that do
not match the backend code (e.g. `/api/v2/sessions/me` vs the actual
`/api/v2/sessions/current`; `/api/v2/projects/{project_id}/draft` vs the actual
`/api/v2/research-contract-drafts/{draft_id}`; `/api/v2/public/shares/{token}`
vs the actual `/api/v2/shares/{share_token}`). The authoritative operationId
naming and paths are the camelCase identifiers in
`apps/api/src/app/routers/*.py` and the generated OpenAPI in
`packages/schemas/generated/v2-core/openapi.json`. This matrix uses the
authoritative camelCase naming throughout.

---

## Summary of gaps (M1 required set, HEAD 9f3380f + #131)

**Backend runtime — all 27 contract operationIds now Implemented.**
#121 mounted `research.router`/`snapshots.router` for the original 24. #131 added
`listResearchProjects`, `createResearchProject` (POST /projects) and
`createResearchContractDraft` (POST /projects/{id}/contract-drafts) on the same
router and `ResearchApplicationService`, reusing the existing Idempotency-Key
replay convention and the `research_projects`/`research_contract_drafts` tables
(migration `20260728_0006` adds only nullable `idempotency_key`/`request_hash`
columns; no table restructure).

**test-only bootstrap responsibility narrowed (#131):** the bootstrap no longer
injects Project, ContractDraft, Contract, Run, credentials or Share tokens. It
publishes only the frozen main case's deterministic `demo_replay`/`fixture`
ArtifactVersion + Evidence onto a *session-owned demo_replay run* created through
the public runtime (`POST /api/v2/test/bootstrap?run_id=`), through the real
Persistence/Publisher boundary. It stays mounted only under `APP_ENV=test`/
`integration`, returns 404 in development/production, never enters the generated
contract, rejects live runs (409) and cross-session runs (hidden 404), and never
returns or logs a credential or share token.

**Persistence — PostgreSQL-backed for research resources; InMemory for Session/Workspace/Share:**
- PostgreSQL: ResearchProject, ResearchContractDraft (model added by #121),
  ResearchContract (stores full frozen content), ResearchRun, RunEvent,
  ResearchArtifact, ArtifactVersion, Evidence, SourceSnapshot.
- InMemory: SessionStore (`security.py`), SnapshotStore (`InMemorySnapshotStore`).
  These lose state on restart and do not share across processes. This is a known
  M1 limitation documented in RISK_REGISTER, not an X-01 blocker.

**Frontend adapter — all previously identified defects fixed by #124/#126:**
- Session revoke path: `DELETE /api/v2/sessions/current` ✓
- Draft PATCH: `If-Match` header sent ✓
- Contract confirm: `Idempotency-Key` header sent ✓
- Run create: `Idempotency-Key` header sent ✓
- `getContractById`: real `GET /api/v2/research-contracts/{id}` ✓
- `evidence.getById`: enabled (no longer throws) ✓
- `artifacts.listByRun`: correct method name and shape ✓
- Workspace `save`: `If-Match` sent as integer string ✓
- Share `create`: DTO→Domain mapper applied ✓
- Share `getPublic`: correct path `/api/v2/shares/{token}` ✓
- Run Event recovery: capped to `sequence <= latest_event_sequence` ✓
- No `as any` casts in snapshot/share repositories ✓
- `api-contract-extensions.ts` (hand-written request types) removed; all request
  bodies use generated DTO types ✓

**Frontend consumer/UI:** `apps/workspace` workspace shell wired to RepositorySet;
`/share/$shareToken` read-only view implemented; WorkspaceController manages
loading, saving, conflict and selection state. Session/HTTP adapter selection
wired via composition root.

**Tests / integration:**
- `test_x01_integration_postgres.py`: 20 contract behavior tests against real
  PostgreSQL + FastAPI ✓
- `tests/e2e-integration/x01-http.spec.ts`: Playwright browser HTTP E2E ✓
- Fixture/HTTP parity: consistency tests verify same Domain Model ✓
- Compose ephemeral project: zero-conflict auto-migration startup + tests ✓

**Remaining limitations (not X-01 blockers):**
- Session/Workspace/Share persistence is InMemory (documented in RISK_REGISTER).
- No SSE (M1 uses cursor-based polling per API_CONTRACT.md §9).
- `getSourceSnapshot`, `getPaperCollection`, `listPaperCollectionCandidates`
  are backend-Implemented but out of minimal M1 UI scope (no frontend consumer).
- Frontend `list`/`create` for Project, `createDraft`, `listRuns`, `saveVersion`,
  `appendEvent` have no contract operation — these are intentionally outside the
  24-operationId M1 required set.
