import { describe, expect, it, vi, beforeEach } from "vitest";
import { apiFetch, ApiError } from "@/lib/api";

function mockResponse(status: number, body: unknown, contentType = "application/json") {
  return Promise.resolve(new Response(
    contentType.includes("json") ? JSON.stringify(body) : String(body),
    { status, headers: { "content-type": contentType } },
  ));
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    try {
      localStorage.removeItem("aiqa_access_token");
    } catch {}
  });

  it("uses credentials and /api base path for protected calls", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(200, { ok: true }));

    await apiFetch("/projects");

    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ credentials: "include" }));
  });

  it("attaches Authorization header if aiqa_access_token exists in localStorage", async () => {
    localStorage.setItem("aiqa_access_token", "test_token");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(200, { ok: true }));

    await apiFetch("/projects");

    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer test_token" })
    }));

  });

  it("dispatches auth-error event on 401 response", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(401, { detail: "unauthorized" }));
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");

    await expect(apiFetch("/projects")).rejects.toMatchObject({ kind: "auth" });

    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: "auth-error" }));
  });

  it("keeps auth routes outside the /api base path", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(200, { authenticated: false }));

    await apiFetch("/status", { authRoute: true });

    expect(fetchMock).toHaveBeenCalledWith("/auth/status", expect.objectContaining({ credentials: "include" }));
  });

  it.each([
    [401, "auth"],
    [403, "forbidden"],
    [404, "not_found"],
    [422, "validation"],
    [500, "server"],
  ] as const)("maps HTTP %s to %s errors", async (status, kind) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(status, { detail: "hidden" }));

    await expect(apiFetch("/projects")).rejects.toMatchObject({ kind });
  });

  it("handles non-JSON error responses safely", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => mockResponse(500, "boom", "text/plain"));

    await expect(apiFetch("/projects")).rejects.toBeInstanceOf(ApiError);
  });

  it("maps network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

    await expect(apiFetch("/projects")).rejects.toMatchObject({ kind: "network" });
  });
});
