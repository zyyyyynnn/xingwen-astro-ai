import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useRouteContext } from "@tanstack/react-router";
import type { RepositorySet } from "@xingwen/data-access";

import { ResearchShell } from "../components/research-shell";
import { usePrivateSession } from "../hooks/use-private-session";
import { NEW_DRAFT_CONTRACT_INPUT } from "../research-defaults";

type Project = NonNullable<
  Awaited<ReturnType<RepositorySet["projects"]["getById"]>>
>;

interface ProjectLoad {
  readonly attempt: number;
  readonly projects: readonly Project[] | null;
  readonly error: boolean;
}

type ListState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly projects: readonly Project[] };

function newActionKey(scope: string): string {
  return `${scope}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

/**
 * Workspace entry: the public Authoring Chain starting point.
 *
 * Lists the current session's projects, creates a new project, and creates an
 * editable draft bound to a chosen project — then routes into the Guided Tour
 * with the real ids. No test-only bootstrap and no fabricated ids are involved;
 * the fixture adapter serves the same chain deterministically.
 */
export function EntryPage() {
  const runtime = useRouteContext({ from: "/" });
  const navigate = useNavigate();
  const sessionState = usePrivateSession(runtime);
  const [load, setLoad] = useState<ProjectLoad | null>(null);
  const [reloadAttempt, setReloadAttempt] = useState(0);
  const [projectName, setProjectName] = useState("");
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // Idempotency keys are stable per logical action and reused across retries
  // (e.g. after a network timeout) so the server replays instead of creating a
  // duplicate; they reset only once the action succeeds. Project keys are
  // keyed by the trimmed name; draft keys by the target project id.
  const projectKeyRef = useRef<{ name: string; key: string } | null>(null);
  const draftKeysRef = useRef<Map<string, string>>(new Map());

  const ready = sessionState.status === "ready";

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await runtime.repositories.projects.list();
        if (!cancelled) {
          setLoad({
            attempt: reloadAttempt,
            projects: page.items,
            error: false,
          });
        }
      } catch {
        if (!cancelled) {
          setLoad({ attempt: reloadAttempt, projects: null, error: true });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, reloadAttempt, runtime.repositories]);

  const current = load?.attempt === reloadAttempt ? load : null;
  const listState: ListState = !ready
    ? { status: "loading" }
    : current === null
      ? { status: "loading" }
      : current.error
        ? { status: "error" }
        : { status: "ready", projects: current.projects ?? [] };

  const createProject = useCallback(async () => {
    const name = projectName.trim();
    if (!ready || pending || name.length === 0) return;
    if (projectKeyRef.current?.name !== name) {
      projectKeyRef.current = { name, key: newActionKey("create-project") };
    }
    setPending(true);
    setActionError(null);
    try {
      await runtime.repositories.projects.create({
        name,
        description: "",
        caseKey: "exoplanet_host_star" as Project["caseKey"],
        idempotencyKey: projectKeyRef.current.key,
      });
      projectKeyRef.current = null;
      setProjectName("");
      setReloadAttempt((attempt) => attempt + 1);
    } catch {
      setActionError("无法创建 Project，请重试。");
    } finally {
      setPending(false);
    }
  }, [pending, projectName, ready, runtime.repositories]);

  const startDraft = useCallback(
    async (project: Project) => {
      if (!ready || pending) return;
      const projectId = String(project.id);
      let draftKey = draftKeysRef.current.get(projectId);
      if (draftKey === undefined) {
        draftKey = newActionKey("create-draft");
        draftKeysRef.current.set(projectId, draftKey);
      }
      setPending(true);
      setActionError(null);
      try {
        const draft = await runtime.repositories.contracts.createDraft(
          project.id,
          {
            intent: NEW_DRAFT_CONTRACT_INPUT.researchGoal,
            contract: NEW_DRAFT_CONTRACT_INPUT,
            idempotencyKey: draftKey,
          },
        );
        draftKeysRef.current.delete(projectId);
        await navigate({
          to: "/tour",
          search: { projectId, draftId: String(draft.id) },
        });
      } catch {
        setActionError("无法创建 Draft，请重试。");
        setPending(false);
      }
    },
    [navigate, pending, ready, runtime.repositories],
  );

  const projects =
    listState.status === "ready" ? listState.projects : ([] as const);

  return (
    <ResearchShell
      status={
        sessionState.status === "loading"
          ? "正在建立会话"
          : sessionState.status === "error"
            ? "会话不可用"
            : sessionState.status === "expired"
              ? "会话已过期"
              : runtime.adapterKind === "fixture"
                ? "Fixture / Demo Replay"
                : "HTTP 适配器"
      }
      atlas={
        <>
          <p className="region-label">Projects</p>
          <p className="region-placeholder">
            {listState.status === "ready"
              ? `${String(projects.length)} 个 Project`
              : "读取中"}
          </p>
        </>
      }
      observatory={
        <p className="region-placeholder">创建或选择 Project 后进入引导。</p>
      }
      console={
        <p className="region-placeholder">
          在入口创建 Project 与 Draft，再进入引导确认 Contract。
        </p>
      }
    >
      <section className="route-content" aria-labelledby="route-title">
        <h1 id="route-title">科研工作台入口</h1>
        <p>创建研究 Project，为其建立 Contract Draft，再进入引导完成确认。</p>

        {sessionState.status === "loading" && <p>正在准备私有研究上下文。</p>}
        {(sessionState.status === "error" ||
          sessionState.status === "expired") && (
          <section className="alert-panel" role="alert">
            <p>
              {sessionState.status === "expired"
                ? "会话已过期，请重新建立研究上下文。"
                : "无法建立研究会话。"}
            </p>
            <button type="button" onClick={sessionState.retry}>
              重新建立会话
            </button>
          </section>
        )}

        {ready && (
          <section
            className="work-panel"
            aria-labelledby="create-project-title"
          >
            <h2 id="create-project-title">新建 Project</h2>
            <label>
              Project 名称
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                disabled={pending}
                aria-invalid={projectName.trim().length === 0}
              />
            </label>
            <div className="action-row">
              <button
                type="button"
                onClick={() => void createProject()}
                disabled={pending || projectName.trim().length === 0}
              >
                创建 Project
              </button>
            </div>
          </section>
        )}

        {ready && (
          <section className="work-panel" aria-labelledby="project-list-title">
            <h2 id="project-list-title">已有 Project</h2>
            {listState.status === "loading" && <p>正在读取 Project 列表。</p>}
            {listState.status === "error" && (
              <div className="alert-panel" role="alert">
                <p>无法读取 Project 列表。</p>
                <button
                  type="button"
                  onClick={() => setReloadAttempt((attempt) => attempt + 1)}
                >
                  重新读取
                </button>
              </div>
            )}
            {listState.status === "ready" && projects.length === 0 && (
              <p>尚无 Project，请先在上方创建。</p>
            )}
            {listState.status === "ready" && projects.length > 0 && (
              <ul className="event-list" aria-label="Project 列表">
                {projects.map((project) => (
                  <li key={String(project.id)}>
                    <span>{project.name}</span>
                    <button
                      type="button"
                      onClick={() => void startDraft(project)}
                      disabled={pending}
                    >
                      创建 Draft 并进入引导
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {actionError && <p role="alert">{actionError}</p>}
      </section>
    </ResearchShell>
  );
}
