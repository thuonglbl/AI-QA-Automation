import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { SessionMatrix } from "@/types/session";

const listSessions = vi.fn();
const deleteSession = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/sessions", () => ({
  listSessions: (...a: unknown[]) => listSessions(...a),
  deleteSession: (...a: unknown[]) => deleteSession(...a),
}));

import { SessionMatrixPanel } from "../SessionMatrixPanel";

const MATRIX: SessionMatrix = {
  environments: [
    { name: "Test 1", url: "https://t1.app" },
    { name: "Prod", url: "https://prod.app" },
  ],
  app_roles: ["Admin", "User"],
  captured: [
    {
      environment: "Test 1",
      role: "Admin",
      auth_method: "TEST_ACCOUNT",
      captured_at: "2026-06-21T00:00:00Z",
      expires_at: "2026-06-21T01:00:00Z",
      last_validated_at: null,
      cookie_count: 3,
    },
  ],
};

function renderPanel() {
  return render(
    <SessionMatrixPanel projectId="p1" projectName="Alpha" open onClose={() => {}} />,
  );
}

describe("SessionMatrixPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listSessions.mockResolvedValue(MATRIX);
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <SessionMatrixPanel projectId="p1" open={false} onClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(listSessions).not.toHaveBeenCalled();
  });

  it("renders a matrix table with environment columns and role rows", async () => {
    renderPanel();
    expect(await screen.findByRole("columnheader", { name: "Test 1" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Prod" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "User" })).toBeInTheDocument();
  });

  it("shows ✓ Logged in for a cached session and Not logged in for missing cache", async () => {
    renderPanel();
    await screen.findByRole("columnheader", { name: "Test 1" });
    expect(screen.getByText(/✓ Logged in/)).toBeInTheDocument();
    // 3 cells should be Not logged in
    expect(screen.getAllByText("Not logged in")).toHaveLength(3);
  });

  it("offers a Clear cache affordance for a cached session", async () => {
    renderPanel();
    await screen.findByRole("columnheader", { name: "Test 1" });
    expect(screen.getByRole("button", { name: "Clear cache" })).toBeInTheDocument();
    
    fireEvent.click(screen.getByRole("button", { name: "Clear cache" }));
    await waitFor(() => expect(deleteSession).toHaveBeenCalledWith("p1", "Test 1", "Admin"));
  });
});
