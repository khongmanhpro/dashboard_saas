import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, readCookie } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "fp_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("readCookie", () => {
  it("đọc đúng cookie trong chuỗi", () => {
    expect(readCookie("fp_csrf", "a=1; fp_csrf=abc%3D; b=2")).toBe("abc=");
    expect(readCookie("missing", "a=1")).toBeNull();
  });
});

describe("api", () => {
  it("gửi CSRF token cho request ghi, không gửi cho GET", async () => {
    document.cookie = "fp_csrf=token123";
    const fetchMock = stubFetch(200, { ok: true });
    await api("/api/me");
    expect(fetchMock.mock.calls[0]![1].headers["X-CSRF-Token"]).toBeUndefined();
    await api("/api/auth/logout", { method: "POST" });
    expect(fetchMock.mock.calls[1]![1].headers["X-CSRF-Token"]).toBe("token123");
    expect(fetchMock.mock.calls[1]![1].credentials).toBe("same-origin");
  });

  it("chuyển lỗi backend thành ApiError có mã", async () => {
    stubFetch(429, { detail: { code: "too_many_attempts", retry_after: 120 } });
    const error = (await api("/api/auth/login", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(429);
    expect(error.code).toBe("too_many_attempts");
    expect(error.detail.retry_after).toBe(120);
  });

  it("báo lỗi mạng", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const error = (await api("/api/me").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("network");
  });

  it("204 trả về undefined", async () => {
    stubFetch(204, undefined);
    await expect(api("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});
