import { ARTIFACT_KINDS } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import {
  artifactRendererRegistry,
  createArtifactRendererRegistry,
  resolveArtifactRenderer,
} from "./artifact-renderer-registry";

describe("Artifact Renderer Registry", () => {
  it("exhaustively registers every current ArtifactKind exactly once", () => {
    expect(new Set(artifactRendererRegistry.keys())).toEqual(
      new Set(ARTIFACT_KINDS),
    );
    expect(artifactRendererRegistry.size).toBe(ARTIFACT_KINDS.length);
    expect(resolveArtifactRenderer("paper_summary")?.capability).toBe(
      "supported",
    );
    expect(resolveArtifactRenderer("graph")?.FullscreenRenderer).toBeTypeOf(
      "function",
    );
  });

  it("rejects missing and duplicate registrations", () => {
    const registrations = [...artifactRendererRegistry.values()];
    const removed = registrations[0];
    if (!removed) throw new Error("No registrations found");

    expect(() =>
      createArtifactRendererRegistry(registrations.slice(1)),
    ).toThrow(`Missing Artifact renderers: ${removed.kind}`);
    expect(() =>
      createArtifactRendererRegistry([...registrations, removed]),
    ).toThrow(`Duplicate Artifact renderer: ${removed.kind}`);
  });

  it("fails unknown kinds safely without inventing a renderer", () => {
    expect(resolveArtifactRenderer("not_an_artifact")).toBeNull();
  });
});
