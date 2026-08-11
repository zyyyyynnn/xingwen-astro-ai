import { describe, expect, it } from "vitest";

import { paperSummaryReadFixture } from "../src/fixture/paper-summary";
import { ValidationError } from "../src/errors";
import { assemblePaperSummaryReview } from "../src/paper-summary-repository";

function cachedRead() {
  const read = structuredClone(paperSummaryReadFixture);
  const snapshot = read.source_snapshots[0]!;
  read.source_mode = "cached";
  snapshot.cache_version = "cache-fixture";
  snapshot.request_metadata = {
    ...snapshot.request_metadata,
    origin_run_id: "run-origin",
    origin_artifact_version_id: "version-origin",
  };
  read.cache_audits = [
    {
      source_id: snapshot.source_id,
      source_snapshot_id: snapshot.id,
      cache_version: snapshot.cache_version,
      cache_applicability: "same normalized query",
      live_failure_class: "timeout",
      live_failure_code: "CROSSREF_TIMEOUT",
      origin_run_id: "run-origin",
      origin_artifact_version_id: "version-origin",
    },
  ];
  return read;
}

describe("assemblePaperSummaryReview — cache audit integrity", () => {
  it("rejects a cached summary without complete cache audit context", () => {
    const read = structuredClone(paperSummaryReadFixture);
    read.source_mode = "cached";
    read.cache_audits = [];

    expect(() => assemblePaperSummaryReview(read)).toThrowError(
      ValidationError,
    );
  });

  it("rejects cache audit context on a non-cached summary", () => {
    const read = structuredClone(paperSummaryReadFixture);
    read.cache_audits = [
      {
        source_id: "crossref",
        source_snapshot_id: "snapshot-cached",
        cache_version: "cache-fixture",
        cache_applicability: "same normalized query",
        live_failure_class: "timeout",
        live_failure_code: "CROSSREF_TIMEOUT",
        origin_run_id: "run-origin",
        origin_artifact_version_id: "version-origin",
      },
    ];

    expect(() => assemblePaperSummaryReview(read)).toThrowError(
      ValidationError,
    );
  });

  it("rejects a cached audit attributed to a different source", () => {
    const read = cachedRead();
    read.cache_audits[0]!.source_id = "semantic-scholar";

    expect(() => assemblePaperSummaryReview(read)).toThrowError(
      ValidationError,
    );
  });
});
