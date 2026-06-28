import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/components/auth/LoginPage";
import { AuthProvider } from "@/contexts/AuthContext";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

const originalLocation = window.location;

function stubLocation(search: string): { assign: ReturnType<typeof vi.fn> } {
  const assign = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, search, assign },
  });
  return { assign };
}

describe("LoginPage (SSO-only)", () => {
  beforeEach(() => {
    // AuthProvider checks /auth/status on mount — return unauthenticated.
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      jsonResponse({ authenticated: false }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("renders a single Sign in with SSO button and no password field", async () => {
    stubLocation("");
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    const button = await screen.findByRole("button", {
      name: /sign in with sso/i,
    });
    expect(button).toBeTruthy();
    // SSO-only: no email/password inputs remain.
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.querySelector('input[type="email"]')).toBeNull();
  });

  it("navigates to the backend SSO endpoint when clicked", async () => {
    const { assign } = stubLocation("");
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    const button = await screen.findByRole("button", {
      name: /sign in with sso/i,
    });
    fireEvent.click(button);
    expect(assign).toHaveBeenCalledWith("/auth/sso/login");
  });

  it("shows a friendly error when the callback redirected with ?sso_error", async () => {
    stubLocation("?sso_error=not_provisioned");
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).toMatch(/not provisioned/i);
  });
});
