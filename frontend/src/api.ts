import type { Scope, SleepDashboard, SportDashboard } from "./types";

const API_ROOT = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

/**
 * 允许从 curl、Swagger 或现有配置中直接粘贴完整 Authorization 值，
 * 但对外请求始终只发送一个 Bearer 前缀。
 */
export function normalizeApiKey(value: string): string {
  const trimmed = value.trim();
  const matched = trimmed.match(/^(?:authorization\s*:\s*)?bearer\s+(.+)$/i);
  return (matched?.[1] ?? trimmed).trim();
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = "请求失败，请稍后重试";
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // 保留通用错误文案。
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function dashboardQuery(scope: Scope, period: string, page: number): string {
  const params = new URLSearchParams({ scope, page: String(page), page_size: "12" });
  if (scope !== "all") params.set("period", period);
  return params.toString();
}

export function getSleepDashboard(token: string, scope: Scope, period: string, page: number) {
  return request<SleepDashboard>(`/rest-records/sessions?${dashboardQuery(scope, period, page)}`, token);
}

export function deleteSleepSession(token: string, id: string) {
  return request<{ deleted_count: number }>(`/rest-records/sessions/${id}`, token, {
    method: "DELETE",
  });
}

export function getSportDashboard(token: string, scope: Scope, period: string, page: number) {
  return request<SportDashboard>(`/sport-records/?${dashboardQuery(scope, period, page)}`, token);
}
