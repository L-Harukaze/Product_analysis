/**
 * 请求底座：VITE_USE_MOCK 切换 mock / 真实 API（README）。
 * 未设置环境变量时默认 mock——断网可跑完整演示（FRONTEND.md §7.1）。
 */

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

const BASE = '/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
  }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    const { mockRequest } = await import('../mocks/handlers');
    return mockRequest<T>(method, path, body);
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => null));
  }
  return res.json() as Promise<T>;
}
