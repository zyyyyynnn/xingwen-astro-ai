import React, { useState, useMemo } from "react";
import { CanvasShell } from "@xingwen/research-canvas";
import type {
  ResearchCanvasViewModel,
  MainStageViewModel,
} from "@xingwen/research-canvas";
import type { WorkspacePageProps } from "./workspace-page";

// @ts-expect-error - Import fixture outside project root
import fixtureData from "../../../../packages/data-access/src/fixture/paper-summary.fixture.json";

export function PreviewPage(_props: WorkspacePageProps) {
  const [stage, setStage] = useState<"completion" | "artifact" | "source">(
    "completion",
  );
  const [selectedStatementId, setSelectedStatementId] = useState<string | null>(
    null,
  );
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [contextMode, setContextMode] = useState<
    "hidden" | "summary" | "detail"
  >("summary");

  const viewModel = useMemo<ResearchCanvasViewModel>(() => {
    const summaryData = fixtureData.read.summary;

    // Map findings
    const mapStatement = (stmt: any) => ({
      statementId: stmt.statement_id,
      text: stmt.text,
      evidenceIds: stmt.evidence_ids,
      status: stmt.status as any,
    });

    const completionStage: MainStageViewModel = {
      type: "completion",
      data: {
        researchGoal: summaryData.research_goal.text,
        status: "completed",
        conclusion:
          "The paper delivers The Revised TESS Input Catalog and Candidate Target List to prioritize TESS targets. It compiles stellar parameters from photometric catalogs and parallax measurements.",
        findings: summaryData.findings.map(mapStatement),
        limitations: summaryData.limitations.map(mapStatement),
        futureWork: summaryData.future_work.map(mapStatement),
        unresolvedQuestions: ["Is there any missing data for non-dwarf stars?"],
        nextSteps: [
          "Review target list for specific planetary transit signatures",
        ],
        finalArtifactId: summaryData.summary_id,
        finalArtifactTitle: "Paper Summary: The Revised TESS Input Catalog",
        hasReproducibility: false,
        isDeriveMissionAvailable: false,
      },
    };

    const artifactStage: MainStageViewModel = {
      type: "artifact",
      data: {
        artifactId: summaryData.summary_id,
        title: "The Revised TESS Input Catalog and Candidate Target List",
        kind: "Paper Summary",
        version: 1,
        status: "Final",
        content: (
          <div className="text-slate-300">
            <p>
              <strong>Goal:</strong>{" "}
              <span
                data-statement-id={summaryData.research_goal.statement_id}
                className="cursor-pointer hover:bg-blue-900/30 border-b border-blue-500/50 pb-0.5"
              >
                {summaryData.research_goal.text}
              </span>
            </p>
            <p className="mt-4">
              <strong>Method:</strong>{" "}
              <span
                data-statement-id={summaryData.method.statement_id}
                className="cursor-pointer hover:bg-blue-900/30 border-b border-blue-500/50 pb-0.5"
              >
                {summaryData.method.text}
              </span>
            </p>
            <p className="mt-4">
              <strong>Dataset:</strong>{" "}
              <span
                data-statement-id={summaryData.dataset.statement_id}
                className="cursor-pointer hover:bg-blue-900/30 border-b border-blue-500/50 pb-0.5"
              >
                {summaryData.dataset.text}
              </span>
            </p>
            <h3 className="text-xl font-bold mt-6 mb-2 text-white">Findings</h3>
            <ul className="list-disc pl-5">
              {summaryData.findings.map((f: any) => (
                <li key={f.statement_id} className="mt-2">
                  <span
                    data-statement-id={f.statement_id}
                    className="cursor-pointer hover:bg-blue-900/30 border-b border-blue-500/50 pb-0.5"
                  >
                    {f.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ),
        isReviewAvailable: false,
        isSourceAvailable: true,
        isCompareAvailable: false,
        isExportAvailable: true,
      },
    };

    const sourceStage: MainStageViewModel = {
      type: "source",
      data: {
        availableExtracts: [
          {
            text: "The paper delivers The Revised TESS Input Catalog and Candidate Target List...",
            location: "Crossref Metadata",
          },
        ],
        isFullSourceAvailable: false,
        missingContractMessage:
          "Full source contract not available for this evidence.",
      },
    };

    let activeStage: MainStageViewModel = completionStage;
    if (stage === "artifact") activeStage = artifactStage;
    if (stage === "source") activeStage = sourceStage;

    let detailContent: React.ReactNode = null;
    if (contextMode === "detail" && selectedStatementId) {
      // Find the statement
      const allStatements = [
        summaryData.research_goal,
        summaryData.method,
        summaryData.dataset,
        ...summaryData.findings,
        ...summaryData.limitations,
        ...summaryData.future_work,
      ];
      const stmt = allStatements.find(
        (s: any) => s.statement_id === selectedStatementId,
      );
      if (stmt) {
        detailContent = (
          <div className="space-y-4">
            <h3 className="font-bold text-lg text-white">Evidence Lens</h3>
            <div className="p-4 bg-slate-900 border border-slate-700 rounded-md">
              <div className="text-sm text-slate-400 mb-2">Statement</div>
              <p className="text-slate-200">{stmt.text}</p>
              <div
                className={`mt-3 inline-block px-2 py-1 text-xs rounded-full font-semibold uppercase tracking-wider ${stmt.status === "supported" ? "bg-green-900/50 text-green-400" : stmt.status === "unverifiable" ? "bg-yellow-900/50 text-yellow-400" : "bg-red-900/50 text-red-400"}`}
              >
                {stmt.status}
              </div>
            </div>

            <h4 className="font-semibold text-white mt-6">Sources</h4>
            {stmt.evidence_ids.length > 0 ? (
              stmt.evidence_ids.map((id: string) => (
                <div
                  key={id}
                  className="p-4 bg-slate-900 border border-slate-800 rounded-md"
                >
                  <div className="text-sm font-medium text-slate-300 mb-2">
                    Extracted Quote
                  </div>
                  <p className="text-sm text-slate-400 italic border-l-2 border-slate-600 pl-3">
                    "The Revised TESS Input Catalog and Candidate Target
                    List..."
                  </p>
                  <button
                    className="mt-4 text-xs text-blue-400 hover:text-blue-300 font-medium"
                    data-source-id={id}
                  >
                    View Full Source →
                  </button>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No evidence provided.</p>
            )}
          </div>
        );
      }
    }

    return {
      navigation: {
        pinnedProjects: ["proj_01JEXAMPLE"],
        recentProjects: ["proj_02"],
        projects: [
          {
            id: "proj_01JEXAMPLE",
            name: "TESS Target List Analysis",
            userStatus: "completed",
            updatedAt: new Date().toISOString(),
          },
          {
            id: "proj_02",
            name: "Exoplanet Demographics",
            userStatus: "draft",
            updatedAt: new Date().toISOString(),
          },
        ],
      },
      mission: {
        projectId: "proj_01JEXAMPLE",
        projectName: "TESS Target List Analysis",
        runId: "run_01",
        status: "completed",
        executionMode: "auto",
      },
      lifecycle: {
        currentPhase: "completion",
        progress: 100,
      },
      stage: activeStage,
      context: {
        mode: contextMode,
        summaries: [
          {
            type: "final_artifact",
            title: "Final Artifact",
            description: "Paper Summary: The Revised TESS Input Catalog",
            isComplete: true,
          },
          {
            type: "evidence",
            title: "Evidence Set",
            description: "4 sources, 3 verified",
            isComplete: true,
          },
          {
            type: "reproducibility",
            title: "Reproducibility Capsule",
            description: "Not generated",
            isComplete: false,
          },
        ],
        detailContent,
      },
      composer: {
        mode: "docked",
        isAvailable: false,
      },
    };
  }, [stage, contextMode, selectedStatementId, selectedSourceId]);

  return (
    <CanvasShell
      viewModel={viewModel}
      onSelectMission={() => {}}
      onSelectArtifact={() => {
        setStage("artifact");
      }}
      onSelectStatement={(id) => {
        setSelectedStatementId(id);
        setContextMode("detail");
      }}
      onSelectSource={(id) => {
        setSelectedSourceId(id);
        setStage("source");
      }}
      onBackToArtifact={() => setStage("artifact")}
      onContextDockModeChange={setContextMode}
      onComposerSubmit={() => {}}
    />
  );
}
