import { ARTIFACT_KINDS } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import {
  artifactRendererRegistry,
  createArtifactRendererRegistry,
  resolveArtifactRenderer,
} from "./artifact-renderer-registry";

describe("Artifact Renderer Registry", () => {
  it("exhaustively registers every domain ArtifactKind exactly once", () => {
    expect([...artifactRendererRegistry.keys()]).toEqual(ARTIFACT_KINDS);
    expect(resolveArtifactRenderer("paper_summary")).toMatchObject({
      capability: "supported",
      contentFamily: "paper_summary",
      surfaces: { thread: true, detail: true, textFallback: true },
    });
    for (const kind of [
      "dataset",
      "field_dictionary",
      "source_collection",
    ] as const) {
      expect(resolveArtifactRenderer(kind)).toMatchObject({
        capability: "supported",
        contentFamily: "data",
      });
    }
    for (const kind of [
      "analysis_report",
      "visualization",
      "spectrum",
      "light_curve",
      "model_evaluation",
      "model_artifact",
    ] as const) {
      expect(resolveArtifactRenderer(kind)).toMatchObject({
        capability: "supported",
        contentFamily: "scientific",
      });
    }
    expect(resolveArtifactRenderer("paper_collection")).toMatchObject({
      capability: "supported",
      contentFamily: "paper_collection",
    });
    for (const kind of [
      "literature_claims",
      "literature_relations",
      "reasoning_traces",
    ] as const) {
      expect(resolveArtifactRenderer(kind)).toMatchObject({
        capability: "supported",
        contentFamily: "literature",
      });
    }
    expect(resolveArtifactRenderer("graph")).toMatchObject({
      capability: "supported",
      contentFamily: "graph",
    });
    for (const registration of artifactRendererRegistry.values()) {
      expect(registration.Content).toBeTypeOf("function");
      expect(registration.TextFallback).toBeTypeOf("function");
    }
    expect(resolveArtifactRenderer("export")).toMatchObject({
      capability: "unsupported",
      surfaces: { thread: false, detail: true, textFallback: true },
    });
  });

  it("rejects missing and duplicate registrations", () => {
    const registrations = [...artifactRendererRegistry.values()];
    const firstRegistration = registrations[0];
    if (!firstRegistration) throw new Error("registry unexpectedly empty");
    expect(() =>
      createArtifactRendererRegistry(registrations.slice(1)),
    ).toThrow("Missing Artifact renderers: dataset");

    expect(() =>
      createArtifactRendererRegistry([...registrations, firstRegistration]),
    ).toThrow("Duplicate Artifact renderer: dataset");
  });

  it("rejects unknown kinds instead of falling back to a generic renderer", () => {
    expect(() => resolveArtifactRenderer("not_an_artifact")).toThrow(
      "Unknown Artifact kind: not_an_artifact",
    );
  });
});
