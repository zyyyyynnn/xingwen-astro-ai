import { useEffect, useRef, useState } from "react";
import { Link, useRouteContext } from "@tanstack/react-router";
import type { RepositorySet } from "@xingwen/data-access";
import {
  GUIDED_TOUR_STAGES,
  type GuidedTourStage,
} from "@xingwen/workspace-core";
import { BrandMark } from "@xingwen/ui";

import { MissionSpine } from "../components/mission-spine";
import { ResearchComposer } from "../components/research-composer";
import { WorkspaceShell } from "../components/workspace-shell";
import { useControllerState } from "../hooks/use-controller-state";
import { usePrivateSession } from "../hooks/use-private-session";

type EntityId = Parameters<RepositorySet["projects"]["getById"]>[0];
type Project = NonNullable<
  Awaited<ReturnType<RepositorySet["projects"]["getById"]>>
>;
type Draft = NonNullable<
  Awaited<ReturnType<RepositorySet["contracts"]["getDraftById"]>>
>;
type Contract = NonNullable<
  Awaited<ReturnType<RepositorySet["contracts"]["getContractById"]>>
>;
type ResearchRun = NonNullable<
  Awaited<ReturnType<RepositorySet["runs"]["getById"]>>
>;

export interface TourPageProps {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

interface TourData {
  readonly project: Project;
  readonly draft: Draft;
  readonly contract: Contract | null;
  readonly run: ResearchRun | null;
}

interface TourLoadResult {
  readonly key: string;
  readonly data: TourData | null;
  readonly error: boolean;
}

let runActionSequence = 0;

function toEntityId(value: string | undefined): EntityId | null {
  return value && value.trim() ? (value as EntityId) : null;
}

function stageLabel(stage: string | null): string {
  return stage ? stage.toUpperCase() : "未开始";
}

function tourStageToPhase(stage: string | null): number {
  if (!stage) return 0;
  const index = GUIDED_TOUR_STAGES.indexOf(stage as GuidedTourStage);
  return index === -1 ? 0 : index;
}

export function TourPage({
  projectId: projectIdProp,
  draftId: draftIdProp,
  contractId: contractIdProp,
  runId: runIdProp,
}: TourPageProps) {
  const runtime = useRouteContext({ from: "/tour" });
  const sessionState = usePrivateSession(runtime);
  const tourState = useControllerState(runtime.tour);
  const fixtureContext =
    runtime.adapterKind === "fixture" ? runtime.bootstrap : null;
  const projectId =
    toEntityId(projectIdProp) ?? fixtureContext?.projectId ?? null;
  const draftId = toEntityId(draftIdProp) ?? fixtureContext?.draftId ?? null;
  const contractId =
    toEntityId(contractIdProp) ?? fixtureContext?.contractId ?? null;
  const runId = toEntityId(runIdProp) ?? fixtureContext?.runId ?? null;
  const [loadResult, setLoadResult] = useState<TourLoadResult | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [actionError, setActionError] = useState(false);
  const [intent, setIntent] = useState("");
  const [researchGoal, setResearchGoal] = useState("");
  const [confirmedDraftId, setConfirmedDraftId] = useState<EntityId | null>(
    null,
  );
  const [actionPending, setActionPending] = useState(false);
  const runIdempotencyKey = useRef<string | null>(null);
  const loadKey =
    projectId && draftId
      ? JSON.stringify([
          projectId,
          draftId,
          contractId ?? null,
          runId ?? null,
          loadAttempt,
        ])
      : null;

  useEffect(() => {
    if (sessionState.status !== "ready") return;
    if (!projectId || !draftId || !loadKey) return;

    let cancelled = false;
    void (async () => {
      try {
        const [project, draft, run] = await Promise.all([
          runtime.repositories.projects.getById(projectId),
          runtime.repositories.contracts.getDraftById(draftId),
          runId
            ? runtime.repositories.runs.getById(runId)
            : Promise.resolve(null),
        ]);
        if (cancelled) return;
        if (!project || !draft) {
          setLoadResult({ key: loadKey, data: null, error: false });
          return;
        }
        const resolvedContractId =
          contractId ?? run?.contractId ?? project.activeContractId;
        const contract = resolvedContractId
          ? await runtime.repositories.contracts.getContractById(
              resolvedContractId,
            )
          : null;
        if (cancelled) return;
        setLoadResult({
          key: loadKey,
          data: { project, draft, contract, run },
          error: false,
        });
        setIntent(draft.intent);
        setResearchGoal(draft.contract.researchGoal);
      } catch {
        if (!cancelled) {
          setLoadResult({ key: loadKey, data: null, error: true });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    contractId,
    draftId,
    loadKey,
    projectId,
    runId,
    runtime.repositories,
    sessionState.status,
  ]);

  const currentLoadResult =
    sessionState.status === "ready" && loadResult?.key === loadKey
      ? loadResult
      : null;
  const data = currentLoadResult?.data ?? null;
  const loadError = currentLoadResult?.error ?? false;
  const selectedMode = tourState.mode ?? "demo_replay";
  const draft = data?.draft ?? null;
  const contract = data?.contract ?? null;
  const run = data?.run ?? null;
  const draftEditable =
    sessionState.status === "ready" &&
    draft?.status === "draft" &&
    confirmedDraftId !== draft.id;
  const hasDraftChanges =
    draft !== null &&
    (intent !== draft.intent || researchGoal !== draft.contract.researchGoal);
  const draftInputsValid =
    intent.trim().length > 0 &&
    researchGoal.trim().length >= 4 &&
    researchGoal.trim().length <= 500;

  const sendTourEvent = (event: Parameters<typeof runtime.tour.send>[0]) => {
    try {
      runtime.tour.send(event);
      if (event.type === "selectMode") runIdempotencyKey.current = null;
      setActionError(false);
    } catch {
      setActionError(true);
    }
  };

  const persistDraft = async (currentDraft: Draft): Promise<Draft> => {
    const updated = await runtime.repositories.contracts.updateDraft(
      currentDraft.id,
      currentDraft.version,
      {
        intent: intent.trim(),
        contract: {
          ...currentDraft.contract,
          researchGoal:
            researchGoal.trim() as Draft["contract"]["researchGoal"],
        },
      },
    );
    setLoadResult((current) =>
      current?.key === loadKey && current.data
        ? { ...current, data: { ...current.data, draft: updated } }
        : current,
    );
    setIntent(updated.intent);
    setResearchGoal(updated.contract.researchGoal);
    return updated;
  };

  const saveDraft = async () => {
    if (!draft || !draftEditable || !draftInputsValid || actionPending) return;
    setActionPending(true);
    try {
      await persistDraft(draft);
      setActionError(false);
    } catch {
      setActionError(true);
    } finally {
      setActionPending(false);
    }
  };

  const confirmContract = async () => {
    if (
      !draft ||
      !projectId ||
      !draftEditable ||
      !draftInputsValid ||
      actionPending
    ) {
      return;
    }
    setActionPending(true);
    try {
      const draftToConfirm = hasDraftChanges
        ? await persistDraft(draft)
        : draft;
      const confirmed = await runtime.repositories.contracts.confirm(
        projectId,
        draftToConfirm.id,
        draftToConfirm.version,
      );
      setLoadResult((current) =>
        current?.key === loadKey && current.data
          ? { ...current, data: { ...current.data, contract: confirmed } }
          : current,
      );
      setConfirmedDraftId(draftToConfirm.id);
      setActionError(false);
    } catch {
      setActionError(true);
    } finally {
      setActionPending(false);
    }
  };

  const startRun = async () => {
    if (!projectId || !contract || actionPending) return;
    const idempotencyKey =
      runIdempotencyKey.current ??
      `workspace-run-${Date.now().toString(36)}-${String(++runActionSequence)}`;
    runIdempotencyKey.current = idempotencyKey;
    setActionPending(true);
    try {
      const created = await runtime.repositories.runs.create({
        projectId,
        contractId: contract.id,
        executionMode: selectedMode,
        idempotencyKey,
      });
      runIdempotencyKey.current = null;
      setLoadResult((current) =>
        current?.key === loadKey && current.data
          ? { ...current, data: { ...current.data, run: created } }
          : current,
      );
      setActionError(false);
    } catch {
      setActionError(true);
    } finally {
      setActionPending(false);
    }
  };

  const sessionLabel =
    sessionState.status === "loading"
      ? "正在建立会话"
      : sessionState.status === "error"
        ? "会话不可用"
        : sessionState.status === "expired"
          ? "会话已过期"
          : runtime.adapterKind === "fixture"
            ? "Fixture / Demo Replay"
            : "HTTP 适配器";
  const workspaceSearch = {
    ...(projectId ? { projectId: String(projectId) } : {}),
    ...(draftId ? { draftId: String(draftId) } : {}),
    ...(contract ? { contractId: String(contract.id) } : {}),
    ...(run
      ? { runId: String(run.id) }
      : runId
        ? { runId: String(runId) }
        : {}),
  };

  const handleComposerSubmit = () => {
    sendTourEvent({ type: "next" });
  };

  return (
    <WorkspaceShell
      navigator={
        <nav aria-label="研究导航">
          <p className="region-label">引导阶段</p>
          <p className="region-placeholder">{stageLabel(tourState.stage)}</p>
          <p className="region-placeholder">
            {tourState.visited.length} 个阶段已访问
          </p>
        </nav>
      }
      missionHeader={
        <header className="mission-header" aria-label="研究使命">
          <h2 className="mission-header__title">
            研究引导：{data?.project?.name ?? "未选择项目"}
          </h2>
          <p className="mission-header__goal">
            研究目标：
            {contract?.researchGoal ??
              draft?.contract.researchGoal ??
              "尚无 Contract"}
          </p>
          <div className="mission-header__status-row">
            <span
              className="mission-header__status"
              data-run-status={run?.status ?? "idle"}
            >
              {stageLabel(tourState.stage)}
              {tourState.status === "paused" ? "（已暂停）" : ""}
            </span>
            {run ? (
              <span className="mission-header__progress">
                {run.executionMode} / {run.status} / {run.progress}%
              </span>
            ) : null}
          </div>
        </header>
      }
      missionSpine={
        <MissionSpine
          currentPhase={tourStageToPhase(tourState.stage)}
          onPhaseClick={(phase) => {
            const stage = GUIDED_TOUR_STAGES[phase];
            if (stage) sendTourEvent({ type: "next" });
          }}
        />
      }
      contextRail={
        <div className="research-context-rail">
          <div className="research-context-rail__header">
            <span className="region-label">引导上下文</span>
          </div>
          <p className="region-placeholder">
            Contract: {contract ? `已确认 v${contract.version}` : "等待确认"}
          </p>
          <p className="region-placeholder">
            Run: {run ? `${run.executionMode} / ${run.status}` : "尚未启动"}
          </p>
          <p className="region-placeholder">{sessionLabel}</p>
        </div>
      }
      composer={
        <ResearchComposer
          mode="docked"
          onSubmit={handleComposerSubmit}
          disabled={
            sessionState.status !== "ready" || tourState.status !== "active"
          }
        />
      }
      headerBrand={
        <>
          <BrandMark />
          <nav aria-label="主要导航">
            <Link to="/" activeOptions={{ exact: true }}>
              入口
            </Link>
            <Link to="/tour" search={workspaceSearch}>
              引导
            </Link>
            <Link to="/workspace" search={workspaceSearch}>
              工作区
            </Link>
          </nav>
        </>
      }
      headerActions={
        <div className="console-actions">
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "start", mode: selectedMode })}
            disabled={sessionState.status !== "ready" || actionPending}
          >
            开始引导
          </button>
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "next" })}
            disabled={
              sessionState.status !== "ready" ||
              actionPending ||
              tourState.status !== "active"
            }
          >
            下一步
          </button>
          <Link to="/workspace" search={workspaceSearch}>
            进入工作区
          </Link>
        </div>
      }
    >
      <section
        className="route-content tour-page"
        aria-labelledby="route-title"
      >
        <h1 id="route-title">研究引导</h1>
        <p className="status-line">阶段：{stageLabel(tourState.stage)}</p>
        <ol className="event-list" aria-label="引导阶段">
          {GUIDED_TOUR_STAGES.map((stage) => {
            const status =
              tourState.stage === stage
                ? "当前"
                : tourState.skipped.includes(stage)
                  ? "已跳过"
                  : tourState.visited.includes(stage)
                    ? "已访问"
                    : "待进行";
            return (
              <li
                key={stage}
                aria-current={tourState.stage === stage ? "step" : undefined}
              >
                {stageLabel(stage)}：{status}
              </li>
            );
          })}
        </ol>

        <fieldset className="mode-control">
          <legend>运行方式</legend>
          <label>
            <input
              type="radio"
              name="execution-mode"
              checked={selectedMode === "demo_replay"}
              onChange={() =>
                sendTourEvent({ type: "selectMode", mode: "demo_replay" })
              }
              disabled={sessionState.status !== "ready" || actionPending}
            />
            Demo Replay
          </label>
          <label>
            <input
              type="radio"
              name="execution-mode"
              checked={selectedMode === "live"}
              onChange={() =>
                sendTourEvent({ type: "selectMode", mode: "live" })
              }
              disabled={
                runtime.adapterKind === "fixture" ||
                sessionState.status !== "ready" ||
                actionPending
              }
              aria-describedby={
                runtime.adapterKind === "fixture"
                  ? "fixture-live-unavailable"
                  : undefined
              }
            />
            Live
          </label>
          {runtime.adapterKind === "fixture" && (
            <p id="fixture-live-unavailable">
              Fixture 模式只支持 Demo Replay。
            </p>
          )}
        </fieldset>

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
        {loadError && (
          <section className="alert-panel" role="alert">
            <p>无法读取引导所需的研究上下文。</p>
            <button
              type="button"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
            >
              重新读取引导上下文
            </button>
          </section>
        )}
        {sessionState.status === "ready" && !data && !loadError && (
          <p>
            {projectId && draftId
              ? "正在读取引导上下文。"
              : "缺少 Project 或 Draft 上下文。"}
          </p>
        )}

        {draft && (
          <section className="work-panel" aria-labelledby="draft-title">
            <h2 id="draft-title">Research Contract Draft</h2>
            <label>
              研究意图
              <input
                value={intent}
                onChange={(event) => setIntent(event.target.value)}
                disabled={!draftEditable || actionPending}
                aria-invalid={draftEditable && !draftInputsValid}
                aria-describedby={
                  draftEditable && !draftInputsValid
                    ? "draft-required-fields"
                    : undefined
                }
              />
            </label>
            <label>
              研究目标
              <textarea
                value={researchGoal}
                onChange={(event) => setResearchGoal(event.target.value)}
                disabled={!draftEditable || actionPending}
                aria-invalid={draftEditable && !draftInputsValid}
                aria-describedby={
                  draftEditable && !draftInputsValid
                    ? "draft-required-fields"
                    : undefined
                }
              />
            </label>
            {draftEditable && !draftInputsValid && (
              <p id="draft-required-fields" role="alert">
                研究意图不能为空；研究目标需要 4 至 500 个字符。
              </p>
            )}
            <div className="action-row">
              <button
                type="button"
                onClick={() => void saveDraft()}
                disabled={!draftEditable || !draftInputsValid || actionPending}
              >
                保存草稿
              </button>
              <button
                type="button"
                onClick={() => void confirmContract()}
                disabled={!draftEditable || !draftInputsValid || actionPending}
              >
                确认 Contract
              </button>
            </div>
          </section>
        )}

        {contract && (
          <section className="work-panel" aria-labelledby="contract-title">
            <h2 id="contract-title">已确认 Contract</h2>
            <p>{contract.researchGoal}</p>
            <p>字段：{contract.requestedFields.join("、")}</p>
          </section>
        )}

        {contract && (
          <section className="work-panel" aria-labelledby="run-title">
            <h2 id="run-title">Research Run</h2>
            <p>
              {run
                ? `${run.executionMode} / ${run.status} / ${run.progress}%`
                : "尚未启动"}
            </p>
            <button
              type="button"
              onClick={() => void startRun()}
              disabled={sessionState.status !== "ready" || actionPending}
            >
              启动运行
            </button>
          </section>
        )}

        <div className="action-row">
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "back" })}
            disabled={
              sessionState.status !== "ready" ||
              actionPending ||
              tourState.status !== "active"
            }
          >
            返回
          </button>
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "pause" })}
            disabled={
              sessionState.status !== "ready" ||
              actionPending ||
              tourState.status !== "active"
            }
          >
            暂停
          </button>
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "resume" })}
            disabled={
              sessionState.status !== "ready" ||
              actionPending ||
              tourState.status !== "paused"
            }
          >
            继续
          </button>
          <button
            type="button"
            onClick={() => sendTourEvent({ type: "skip" })}
            disabled={
              sessionState.status !== "ready" ||
              actionPending ||
              tourState.status !== "active"
            }
          >
            跳过本步
          </button>
        </div>
        {actionError && (
          <p role="alert">当前操作未完成，请检查上下文后重试。</p>
        )}
      </section>
    </WorkspaceShell>
  );
}
