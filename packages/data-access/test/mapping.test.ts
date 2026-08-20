import { asEntityId } from "@xingwen/domain";
import type {
  ResearchContractDraft as ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
} from "@xingwen/contracts";
import { describe, expect, it } from "vitest";

import {
  mapDomainContractInputToDto,
  mapResearchContractDraft,
} from "../src/mapping";

function contractInputDto(): ResearchContractInputDto {
  return {
    research_goal: "Compare host-star parameters with traceable evidence",
    target_objects: ["host_star"],
    data_requirements: { unit_policy: "canonical" },
    requested_fields: ["teff"],
    source_scope: { allowed_sources: ["simbad"] },
    paper_search_scope: {
      keywords: ["exoplanet"],
      year_from: 2020,
      year_to: 2026,
      source_ids: [],
      max_candidates: 10,
    },
    scientific_tasks: [
      {
        task_id: "task-light-curve",
        skill_id: "light_curve_acquisition",
        parameters: { target: "Kepler-186", band: "tess" },
        input_refs: ["input-1", "input-2"],
      },
      {
        task_id: "task-period",
        skill_id: "light_curve_analysis",
        parameters: { method: "bls" },
        input_refs: [],
      },
    ],
    output_requirements: ["dataset"],
    evidence_requirements: {
      require_locator: true,
      require_source_snapshot: true,
      minimum_coverage: 1,
    },
    quality_constraints: {
      source_completeness_min: 1,
      unit_consistency_min: 1,
    },
  };
}

describe("scientific task contract mapping", () => {
  it("maps scientific_tasks DTO into complete domain scientificTasks", () => {
    const dto: ResearchContractDraftDto = {
      id: "rcd_01",
      session_id: "sess_01",
      project_id: "proj_01",
      version: 1,
      intent: "宿主星参数比较",
      status: "draft",
      contract: contractInputDto(),
      warnings: [],
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:00:00Z",
      expires_at: "2026-08-19T00:00:00Z",
    };

    const draft = mapResearchContractDraft(dto);

    expect(draft.contract.scientificTasks).toEqual([
      {
        taskId: asEntityId("task-light-curve"),
        skillId: "light_curve_acquisition",
        parameters: { target: "Kepler-186", band: "tess" },
        inputRefs: [asEntityId("input-1"), asEntityId("input-2")],
      },
      {
        taskId: asEntityId("task-period"),
        skillId: "light_curve_analysis",
        parameters: { method: "bls" },
        inputRefs: [],
      },
    ]);
  });

  it("round-trips scientific tasks back to the backend DTO without loss", () => {
    const draft = mapResearchContractDraft({
      id: "rcd_01",
      session_id: "sess_01",
      project_id: "proj_01",
      version: 1,
      intent: "宿主星参数比较",
      status: "draft",
      contract: contractInputDto(),
      warnings: [],
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:00:00Z",
      expires_at: "2026-08-19T00:00:00Z",
    });

    const submitted = mapDomainContractInputToDto(draft.contract);

    expect(submitted.scientific_tasks).toEqual([
      {
        task_id: "task-light-curve",
        skill_id: "light_curve_acquisition",
        parameters: { target: "Kepler-186", band: "tess" },
        input_refs: ["input-1", "input-2"],
      },
      {
        task_id: "task-period",
        skill_id: "light_curve_analysis",
        parameters: { method: "bls" },
        input_refs: [],
      },
    ]);
  });

  it("rejects scientific tasks referencing an unknown skill id", () => {
    const dto: ResearchContractDraftDto = {
      id: "rcd_01",
      session_id: "sess_01",
      project_id: "proj_01",
      version: 1,
      intent: "宿主星参数比较",
      status: "draft",
      contract: {
        ...contractInputDto(),
        scientific_tasks: [
          {
            task_id: "task-x",
            skill_id: "not_a_skill" as never,
            parameters: {},
            input_refs: [],
          },
        ],
      },
      warnings: [],
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:00:00Z",
      expires_at: "2026-08-19T00:00:00Z",
    };

    expect(() => mapResearchContractDraft(dto)).toThrow(TypeError);
  });

  it("preserves nested JSON-compatible parameters across the round trip", () => {
    const contract = contractInputDto();
    contract.scientific_tasks = [
      {
        task_id: "task-nested",
        skill_id: "light_curve_analysis",
        parameters: {
          window: { period_days: 3.5, harmonics: [1, 2, 4] },
          notes: null,
          active: true,
        },
        input_refs: [],
      },
    ];
    const draft = mapResearchContractDraft({
      id: "rcd_01",
      session_id: "sess_01",
      project_id: "proj_01",
      version: 1,
      intent: "宿主星参数比较",
      status: "draft",
      contract,
      warnings: [],
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:00:00Z",
      expires_at: "2026-08-19T00:00:00Z",
    });

    const submitted = mapDomainContractInputToDto(draft.contract);

    expect(submitted.scientific_tasks?.[0]?.parameters).toEqual({
      window: { period_days: 3.5, harmonics: [1, 2, 4] },
      notes: null,
      active: true,
    });
  });

  it("rejects scientific task parameters that are not JSON-compatible", () => {
    const contract = contractInputDto();
    contract.scientific_tasks = [
      {
        task_id: "task-bad",
        skill_id: "light_curve_analysis",
        parameters: { callback: (() => undefined) as never },
        input_refs: [],
      },
    ];

    expect(() =>
      mapResearchContractDraft({
        id: "rcd_01",
        session_id: "sess_01",
        project_id: "proj_01",
        version: 1,
        intent: "宿主星参数比较",
        status: "draft",
        contract,
        warnings: [],
        created_at: "2026-08-18T00:00:00Z",
        updated_at: "2026-08-18T00:00:00Z",
        expires_at: "2026-08-19T00:00:00Z",
      }),
    ).toThrow(/not JSON-compatible/u);
  });
});
