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

export interface PublicFieldIssue {
  readonly field: string;
  readonly code: string;
}

export type PublicApplicationError =
  | {
      readonly kind: "session_required";
      readonly safeMessage: string;
      readonly retryable: true;
    }
  | {
      readonly kind: "forbidden";
      readonly safeMessage: string;
      readonly retryable: false;
    }
  | {
      readonly kind: "not_found";
      readonly safeMessage: string;
      readonly retryable: false;
    }
  | {
      readonly kind: "conflict";
      readonly safeMessage: string;
      readonly retryable: true;
    }
  | {
      readonly kind: "validation";
      readonly safeMessage: string;
      readonly retryable: false;
      readonly fieldIssues: readonly PublicFieldIssue[];
    }
  | {
      readonly kind: "rate_limited";
      readonly safeMessage: string;
      readonly retryable: true;
      readonly retryAfterMs: number | null;
    }
  | {
      readonly kind: "network";
      readonly safeMessage: string;
      readonly retryable: true;
    }
  | {
      readonly kind: "upstream";
      readonly safeMessage: string;
      readonly retryable: true;
    }
  | {
      readonly kind: "unexpected";
      readonly safeMessage: string;
      readonly retryable: true;
    };

const SAFE_MESSAGES = {
  session_required: "需要重新建立会话",
  forbidden: "当前操作不可用",
  not_found: "资源不可用",
  conflict: "资源已发生变化，请刷新后重试",
  validation: "输入未通过校验",
  rate_limited: "请求过于频繁，请稍后重试",
  network: "网络暂不可用，请稍后重试",
  upstream: "研究服务暂不可用，请稍后重试",
  unexpected: "操作暂时不可用，请稍后重试",
} as const;

function unexpectedError(): PublicApplicationError {
  return {
    kind: "unexpected",
    safeMessage: SAFE_MESSAGES.unexpected,
    retryable: true,
  };
}

export function toPublicApplicationError(
  error: unknown,
): PublicApplicationError {
  if (error instanceof SessionExpiredError) {
    return {
      kind: "session_required",
      safeMessage: SAFE_MESSAGES.session_required,
      retryable: true,
    };
  }
  if (error instanceof ForbiddenError) {
    return {
      kind: "forbidden",
      safeMessage: SAFE_MESSAGES.forbidden,
      retryable: false,
    };
  }
  if (error instanceof NotFoundError || error instanceof EntityNotFoundError) {
    return {
      kind: "not_found",
      safeMessage: SAFE_MESSAGES.not_found,
      retryable: false,
    };
  }
  if (error instanceof ConflictError) {
    return {
      kind: "conflict",
      safeMessage: SAFE_MESSAGES.conflict,
      retryable: true,
    };
  }
  if (error instanceof ValidationError) {
    return {
      kind: "validation",
      safeMessage: SAFE_MESSAGES.validation,
      retryable: false,
      fieldIssues: error.fieldErrors.map(({ field, code }) => ({
        field,
        code,
      })),
    };
  }
  if (error instanceof RateLimitedError) {
    return {
      kind: "rate_limited",
      safeMessage: SAFE_MESSAGES.rate_limited,
      retryable: true,
      retryAfterMs: error.retryAfterMs,
    };
  }
  if (error instanceof NetworkError) {
    return {
      kind: "network",
      safeMessage: SAFE_MESSAGES.network,
      retryable: true,
    };
  }
  if (error instanceof UpstreamError) {
    return {
      kind: "upstream",
      safeMessage: SAFE_MESSAGES.upstream,
      retryable: true,
    };
  }
  if (error instanceof UnexpectedHttpError) {
    return unexpectedError();
  }
  if (
    error instanceof FixtureValidationError ||
    error instanceof FixtureSemanticError
  ) {
    return unexpectedError();
  }
  return unexpectedError();
}
