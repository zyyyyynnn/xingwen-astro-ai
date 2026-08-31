import { describe, expect, it } from "vitest";
import {
  modelEvaluationContent,
  scientificArtifactReadsFixture,
} from "../src/fixture/scientific-artifacts";
import { mapScientificArtifactRead } from "../src/scientific-artifact-repository";

describe("scientific model contract mapping", () => {
  it("preserves distinct baseline identity, metric direction and measured diagnostics", () => {
    const read = scientificArtifactReadsFixture.find(
      (item) => item.content.kind === "model_evaluation",
    );
    if (!read) throw new Error("model fixture missing");
    const review = mapScientificArtifactRead({
      ...read,
      content: {
        ...modelEvaluationContent,
        diagnostics: {
          evaluated_sample_count: 4,
          confusion_matrix: {
            labels: ["star", "galaxy"],
            rows: [
              [2, 0],
              [1, 1],
            ],
          },
          regression_predictions: [],
          forecast: [],
        },
      },
    });
    if (review.content.kind !== "model_evaluation")
      throw new Error("wrong model kind");
    const metric = review.content.metrics[0];
    const baseline = review.content.baselineMetrics[0];
    expect(metric.metricId).not.toBe(baseline.metricId);
    expect(metric.metricKey).toBe(baseline.metricKey);
    expect(metric.optimization).toBe("maximize");
    expect(metric.category).toBe("holdout");
    expect(review.content.diagnostics?.confusionMatrix).toEqual({
      labels: ["star", "galaxy"],
      rows: [
        [2, 0],
        [1, 1],
      ],
    });
    expect(review.content.diagnostics?.evaluatedSampleCount).toBe(4);
  });
});
