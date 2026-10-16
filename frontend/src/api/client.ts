export const CSRF_COOKIE = "fp_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;

  constructor(status: number, code: string, detail: Record<string, unknown> = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export function readCookie(name: string, cookieString: string = document.cookie): string | null {
  for (const part of cookieString.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

/** Gọi API cùng origin. Cookie phiên gửi tự động; request ghi kèm CSRF token. */
export async function api<T>(path: string, options: { method?: Method; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "network");
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const d = detail as Record<string, unknown>;
      throw new ApiError(response.status, String(d.code), d);
    }
    throw new ApiError(response.status, response.status === 422 ? "validation" : "unknown");
  }
  return data as T;
}
