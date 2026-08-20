import { describe, expect, it } from "vitest";

import { paperSummaryReadFixture } from "../src/fixture/paper-summary";
import { ValidationError } from "../src/errors";
import {
  assemblePaperSummaryDocumentSource,
  assemblePaperSummaryReview,
} from "../src/paper-summary-repository";

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

describe("assemblePaperSummaryDocumentSource", () => {
  it("preserves an authorized document image as an image source", () => {
    expect(
      assemblePaperSummaryDocumentSource({
        research_input: {
          id: "document-image-1",
          type: "image",
          source_type: "upload",
          content_hash: `sha256:${"1".repeat(64)}`,
          filename: "paper-page.png",
          mime_type: "image/png",
          size_bytes: 128,
          created_at: "2026-08-20T10:00:00Z",
          source_snapshot_id: null,
          status: "accepted",
        },
      }),
    ).toEqual({
      researchInputId: "document-image-1",
      documentKind: "image",
    });
  });

  it("rejects a non-document ResearchInput at the document-source boundary", () => {
    expect(() =>
      assemblePaperSummaryDocumentSource({
        research_input: {
          id: "dataset-1",
          type: "csv",
          source_type: "upload",
          content_hash: `sha256:${"2".repeat(64)}`,
          filename: "measurements.csv",
          mime_type: "text/csv",
          size_bytes: 128,
          created_at: "2026-08-20T10:00:00Z",
          source_snapshot_id: null,
          status: "accepted",
        },
      }),
    ).toThrowError(ValidationError);
  });
});
