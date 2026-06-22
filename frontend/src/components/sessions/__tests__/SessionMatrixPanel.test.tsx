import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { SessionMatrix } from "@/types/session";

const listSessions = vi.fn();
const captureSession = vi.fn().mockResolvedValue({});
const autoCaptureSession = vi.fn().mockResolvedValue({});
const deleteSession = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/sessions", () => ({
  listSessions: (...a: unknown[]) => listSessions(...a),
  captureSession: (...a: unknown[]) => captureSession(...a),
  autoCaptureSession: (...a: unknown[]) => autoCaptureSession(...a),
  deleteSession: (...a: unknown[]) => deleteSession(...a),
}));

import { SessionMatrixPanel } from "../SessionMatrixPanel";

const SSO_MATRIX: SessionMatrix = {
  environments: [{ name: "Test 1", url: "https://t1.app" }],
  app_roles: ["Admin", "User"],
  login_type: "SSO",
  captured: [
    {
      environment: "Test 1",
      role: "Admin",
      auth_method: "SSO_MANUAL",
      captured_at: "2026-06-21T00:00:00Z",
      expires_at: null,
      last_validated_at: null,
      cookie_count: 3,
    },
  ],
};

const PASSWORD_MATRIX: SessionMatrix = {
  environments: [{ name: "Prod", url: "https://prod.app" }],
  app_roles: ["Admin"],
  login_type: "PASSWORD",
  captured: [],
};

function renderPanel() {
  return render(
    <SessionMatrixPanel projectId="p1" projectName="Alpha" open onClose={() => {}} />,
  );
}

describe("SessionMatrixPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listSessions.mockResolvedValue(SSO_MATRIX);
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <SessionMatrixPanel projectId="p1" open={false} onClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(listSessions).not.toHaveBeenCalled();
  });

  it("shows the env×role matrix with captured + not-captured status", async () => {
    renderPanel();
    expect(await screen.findByText("Test 1")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.getByText(/Captured ·/)).toBeInTheDocument();
    expect(screen.getByText("Not captured")).toBeInTheDocument();
    expect(screen.getByText("SSO login")).toBeInTheDocument();
  });

  it("offers manual capture for SSO and no auto-login", async () => {
    renderPanel();
    await screen.findByText("Test 1");
    expect(screen.queryByRole("button", { name: "Auto-login" })).not.toBeInTheDocument();
    // Admin is captured → Re-capture; User is not → Capture.
    expect(screen.getByRole("button", { name: "Re-capture" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Capture" })).toBeInTheDocument();
  });

  it("captures a session over CDP with the resolved request", async () => {
    renderPanel();
    await screen.findByText("Test 1");
    // Open the Admin re-capture form (row button is "Re-capture", so the submit "Capture" is unique).
    fireEvent.click(screen.getByRole("button", { name: "Re-capture" }));
    expect(await screen.findByLabelText(/CDP URL/i)).toHaveValue("http://localhost:9222");
    fireEvent.click(screen.getByRole("button", { name: "Capture now" }));
    await waitFor(() => expect(captureSession).toHaveBeenCalledTimes(1));
    expect(captureSession).toHaveBeenCalledWith("p1", {
      environment: "Test 1",
      role: "Admin",
      auth_method: "SSO_MANUAL",
      cdp_url: "http://localhost:9222",
    });
    // Matrix refetched after the capture.
    expect(listSessions).toHaveBeenCalledTimes(2);
  });

  it("deletes a captured session", async () => {
    renderPanel();
    await screen.findByText("Test 1");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteSession).toHaveBeenCalledWith("p1", "Test 1", "Admin"));
  });

  it("auto-logs-in for PASSWORD projects with the chrome path", async () => {
    listSessions.mockResolvedValue(PASSWORD_MATRIX);
    renderPanel();
    await screen.findByText("Prod");
    expect(screen.getByText("Password login")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Auto-login" }));
    const input = await screen.findByLabelText(/Chrome\/Edge executable path/i);
    fireEvent.change(input, { target: { value: "C:/chrome.exe" } });
    fireEvent.click(screen.getByRole("button", { name: "Auto-login & capture" }));
    await waitFor(() => expect(autoCaptureSession).toHaveBeenCalledTimes(1));
    expect(autoCaptureSession).toHaveBeenCalledWith("p1", {
      environment: "Prod",
      role: "Admin",
      chrome_path: "C:/chrome.exe",
    });
  });
});
