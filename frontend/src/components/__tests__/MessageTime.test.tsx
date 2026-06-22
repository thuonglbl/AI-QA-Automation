import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { MessageTime, NowMessageTime } from "../MessageTime";
import { AuthContext } from "@/contexts/AuthContext";
import type { AuthUser } from "@/lib/auth";

/** Render under an AuthContext carrying a fixed timezone, so formatting is deterministic
 * regardless of the test runner's host zone. A null tz omits the user entirely. */
function renderWithTz(tz: string | undefined, node: ReactNode) {
  const user: AuthUser | null = tz
    ? { email: "t@e.vn", name: "T", timezone: tz }
    : null;
  return render(
    <AuthContext.Provider
      value={{
        isAuthenticated: true,
        user,
        isLoading: false,
        error: null,
        logout: async () => {},
        refresh: async () => {},
        setAuthStatus: () => {},
      }}
    >
      {node}
    </AuthContext.Provider>,
  );
}

const HHMMSS = /^\d{2}:\d{2}:\d{2}$/;

describe("MessageTime", () => {
  it("renders hh:mm:ss in the user's timezone from the users table", () => {
    renderWithTz("UTC", <MessageTime timestamp="2026-04-16T10:00:00Z" />);
    expect(screen.getByText("10:00:00")).toBeInTheDocument();
  });

  it("shifts the displayed time to the user's IANA zone", () => {
    // Asia/Ho_Chi_Minh is UTC+7 with no DST → 10:00:00Z renders as 17:00:00.
    renderWithTz(
      "Asia/Ho_Chi_Minh",
      <MessageTime timestamp="2026-04-16T10:00:00Z" />,
    );
    expect(screen.getByText("17:00:00")).toBeInTheDocument();
  });

  it("renders nothing for a missing timestamp", () => {
    const { container } = renderWithTz("UTC", <MessageTime />);
    expect(container.textContent).toBe("");
  });

  it("renders nothing for an invalid timestamp", () => {
    const { container } = renderWithTz(
      "UTC",
      <MessageTime timestamp="not-a-date" />,
    );
    expect(container.textContent).toBe("");
  });
});

describe("NowMessageTime", () => {
  it("renders a frozen hh:mm:ss for transient bubbles with no backing message", () => {
    const { container } = renderWithTz("UTC", <NowMessageTime />);
    const text = container.textContent ?? "";
    expect(text).toMatch(HHMMSS);
  });
});
