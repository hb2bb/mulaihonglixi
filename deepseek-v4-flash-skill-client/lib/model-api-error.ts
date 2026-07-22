export const CHAT_REQUEST_TIMEOUT_MS = 120_000;
export const AUXILIARY_REQUEST_TIMEOUT_MS = 45_000;

export class ModelUpstreamError extends Error {
  constructor(
    readonly service: string,
    readonly statusCode: number,
  ) {
    super(`${service} upstream HTTP ${statusCode}`);
    this.name = "ModelUpstreamError";
  }
}

type ErrorWithCause = Error & {
  code?: unknown;
  cause?: unknown;
};

export type PublicModelFailure = {
  code: string;
  message: string;
  status: number;
};

function errorCode(error: unknown): string {
  if (!(error instanceof Error)) return "";
  const directCode = (error as ErrorWithCause).code;
  if (typeof directCode === "string") return directCode;
  const cause = (error as ErrorWithCause).cause;
  if (cause instanceof Error) return errorCode(cause);
  return "";
}

export function publicModelFailure(
  error: unknown,
  fallbackService = "模型服务",
): PublicModelFailure {
  if (error instanceof ModelUpstreamError) {
    const service = error.service;
    if (error.statusCode === 400) {
      return {
        code: "upstream_bad_request",
        message: `${service}拒绝了请求（HTTP 400），请检查模型名和请求参数。`,
        status: 502,
      };
    }
    if (error.statusCode === 401 || error.statusCode === 403) {
      return {
        code: "upstream_auth_failed",
        message: `${service}鉴权失败（HTTP ${error.statusCode}），请检查 API Key。`,
        status: 502,
      };
    }
    if (error.statusCode === 402) {
      return {
        code: "upstream_balance_low",
        message: `${service}账户余额不足（HTTP 402）。`,
        status: 502,
      };
    }
    if (error.statusCode === 429) {
      return {
        code: "upstream_rate_limited",
        message: `${service}请求过于频繁（HTTP 429），请稍后重试。`,
        status: 503,
      };
    }
    if (error.statusCode >= 500) {
      return {
        code: "upstream_unavailable",
        message: `${service}暂时不可用（HTTP ${error.statusCode}），请稍后重试。`,
        status: 503,
      };
    }
    return {
      code: "upstream_http_error",
      message: `${service}返回异常状态（HTTP ${error.statusCode}）。`,
      status: 502,
    };
  }

  if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
    return {
      code: "upstream_timeout",
      message: `${fallbackService}请求超时，请稍后重试。`,
      status: 504,
    };
  }

  const code = errorCode(error);
  if (
    error instanceof TypeError ||
    ["ECONNRESET", "ECONNREFUSED", "ENETUNREACH", "EHOSTUNREACH", "ENOTFOUND"].includes(code)
  ) {
    return {
      code: "upstream_network_error",
      message: `无法连接${fallbackService}${code ? `（${code}）` : ""}，请检查代理、VPN、DNS 和网络连接。`,
      status: 502,
    };
  }

  return {
    code: "model_request_failed",
    message: `${fallbackService}调用失败，请稍后重试。`,
    status: 502,
  };
}
