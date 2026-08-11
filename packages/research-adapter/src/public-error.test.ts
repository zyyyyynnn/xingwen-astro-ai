import {
  ConflictError,
  EntityNotFoundError,
  FixtureSemanticError,
  FixtureValidationError,
  ForbiddenError,
  NetworkError,
  NotFoundError,
  RateLimitedError,
  SessionExpiredError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
} from "@xingwen/data-access";
import { describe, expect, it } from "vitest";

import { toPublicApplicationError } from "./public-error";

describe("normalized errors to PublicApplicationError", () => {
  it("maps HTTP and Fixture not-found errors to the same fail-closed semantic", () => {
    const httpError = toPublicApplicationError(
      new NotFoundError("private resource path", "PROJECT_NOT_FOUND"),
    );
    const fixtureError = toPublicApplicationError(
      new EntityNotFoundError("project", "secret"),
    );

    expect(httpError).toEqual(fixtureError);
    expect(httpError).toEqual({
      kind: "not_found",
      safeMessage: "资源不可用",
    });
  });

  it.each([
    [new SessionExpiredError("credential details"), "session_required"],
    [new ForbiddenError("owner session path", "FORBIDDEN"), "forbidden"],
    [new ConflictError("revision 17 conflict", "CONFLICT"), "conflict"],
    [
      new NetworkError("https://private.example/request", new Error("socket")),
      "network",
    ],
    [
      new UpstreamError("upstream request id secret", "UPSTREAM", 503),
      "upstream",
    ],
    [
      new UnexpectedHttpError("SQL select * from secrets", 500, "INTERNAL"),
      "unexpected",
    ],
    [
      new FixtureValidationError("Fixture", ["secret field path"]),
      "unexpected",
    ],
    [
      new FixtureSemanticError("fixture source leaked internal path"),
      "unexpected",
    ],
    [new Error("C:\\private\\repo\\secret.sql"), "unexpected"],
    ["unknown thrown value", "unexpected"],
  ] as const)("maps %s to %s", (error, kind) => {
    const result = toPublicApplicationError(error);

    expect(result.kind).toBe(kind);
    expect(JSON.stringify(result)).not.toMatch(
      /private|secret|sql|socket|request id|credential|path/iu,
    );
  });

  it("does not expose unchecked validation metadata", () => {
    const result = toPublicApplicationError(
      new ValidationError(
        "raw internal validation detail",
        "SCHEMA_VALIDATION_FAILED",
        [
          {
            field: "research_goal",
            code: "too_short",
            message: "do not expose this raw message",
          },
        ],
      ),
    );

    expect(result).toEqual({
      kind: "validation",
      safeMessage: "输入未通过校验",
    });
    const serialized = JSON.stringify(result);
    expect(serialized).not.toContain("research_goal");
    expect(serialized).not.toContain("too_short");
    expect(serialized).not.toContain("raw internal");
    expect("retryable" in result).toBe(false);
  });

  it("preserves only the normalized rate-limit delay", () => {
    expect(
      toPublicApplicationError(new RateLimitedError("internal quota", 1500)),
    ).toEqual({
      kind: "rate_limited",
      safeMessage: "请求过于频繁，请稍后重试",
      retryAfterMs: 1500,
    });
  });

  it.each([
    new SessionExpiredError("credential details"),
    new ConflictError("revision conflict", "CONFLICT"),
    new UnexpectedHttpError("internal details", 500, "INTERNAL"),
    new FixtureValidationError("Fixture", ["private field"]),
    new FixtureSemanticError("private fixture path"),
    new NetworkError("private URL"),
    new UpstreamError("private upstream detail", "UPSTREAM", 503),
  ])("does not add retry policy to %s", (error) => {
    const result = toPublicApplicationError(error);

    expect("retryable" in result).toBe(false);
  });
});
