import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { JackInputSelection } from "../agents/JackInputSelection";
import type { ScriptInput } from "@/types/script";

const ENVS = [{ name: "Production", url: "https://app.example.com" }];
const APP_ROLES = ["Admin", "User"];
const SESSIONS = [{ environment: "Production", role: "Admin" }];

function makeEntry(overrides: Partial<ScriptInput> = {}): ScriptInput {
  return {
    artifact_id: "abc-123",
    name: "test_login.py",
    title: "test_login",
    from_current_thread: true,
    default_selected: true,
    preview: "def test_login(page):\n    page.goto(BASE_URL)",
    source_test_case_title: "Login with valid credentials",
    confidence: 0.92,
    ...overrides,
  };
}

/** Render with the env/role/session props that enable Run by default. */
function renderRunnable(scripts: ScriptInput[], onConfirm = vi.fn()) {
  render(
    <JackInputSelection
      scripts={scripts}
      environments={ENVS}
      appRoles={APP_ROLES}
      sessions={SESSIONS}
      onConfirm={onConfirm}
    />,
  );
  return onConfirm;
}

describe("JackInputSelection", () => {
  describe("Rendering", () => {
    it("renders script title + confidence + source", () => {
      renderRunnable([makeEntry()]);
      expect(screen.getByText("test_login")).toBeInTheDocument();
      expect(screen.getByText("92%")).toBeInTheDocument();
      expect(screen.getByText(/Login with valid credentials/i)).toBeInTheDocument();
    });

    it("shows 'This conversation' badge for current-thread entry", () => {
      renderRunnable([makeEntry()]);
      expect(screen.getByText("This conversation")).toBeInTheDocument();
    });

    it("expands/collapses the .py preview", () => {
      renderRunnable([makeEntry()]);
      fireEvent.click(screen.getByRole("button", { name: /Show preview/i }));
      expect(screen.getByText(/page\.goto\(BASE_URL\)/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Hide preview/i }));
      expect(screen.queryByText(/page\.goto\(BASE_URL\)/i)).not.toBeInTheDocument();
    });
  });

  describe("Environment / role / browsers", () => {
    it("renders an environment dropdown + role dropdown + browser checkboxes", () => {
      renderRunnable([makeEntry()]);
      expect(screen.getByLabelText(/Target environment/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Login role/i)).toBeInTheDocument();
      expect(screen.getByRole("checkbox", { name: "Chromium" })).toBeChecked();
      expect(screen.getByRole("checkbox", { name: "Edge" })).not.toBeChecked();
    });

    it("renders a free-text URL field when no environments are provided", () => {
      render(<JackInputSelection scripts={[makeEntry()]} onConfirm={vi.fn()} />);
      expect(screen.getByLabelText(/Application URL/i)).toBeInTheDocument();
    });
  });

  describe("Session awareness (14.4)", () => {
    it("disables Run + shows hint when no session for the selected (env, role)", () => {
      render(
        <JackInputSelection
          scripts={[makeEntry()]}
          environments={ENVS}
          appRoles={APP_ROLES}
          sessions={[]}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).toBeDisabled();
      expect(screen.getByText(/No captured session for Production \/ Admin/i)).toBeInTheDocument();
    });

    it("enables Run when a session exists for the selected (env, role)", () => {
      renderRunnable([makeEntry()]);
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).not.toBeDisabled();
    });
  });

  describe("Per-script role session hard-block (Slice 6)", () => {
    it("requires a session for the script's OWN role, not the UI default", () => {
      render(
        <JackInputSelection
          scripts={[makeEntry({ role: "User" })]}
          environments={ENVS}
          appRoles={APP_ROLES}
          sessions={SESSIONS} // Admin only
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).toBeDisabled();
      expect(screen.getByText(/No captured session for Production \/ User/i)).toBeInTheDocument();
    });

    it("disables Run when one role in a mixed selection lacks a session", () => {
      render(
        <JackInputSelection
          scripts={[
            makeEntry({ artifact_id: "a", title: "test_admin", role: "Admin" }),
            makeEntry({ artifact_id: "b", title: "test_user", role: "User" }),
          ]}
          environments={ENVS}
          appRoles={APP_ROLES}
          sessions={SESSIONS} // Admin only
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).toBeDisabled();
      expect(screen.getByText(/No captured session for Production \/ User/i)).toBeInTheDocument();
    });

    it("enables Run when every involved role has a session", () => {
      render(
        <JackInputSelection
          scripts={[
            makeEntry({ artifact_id: "a", title: "test_admin", role: "Admin" }),
            makeEntry({ artifact_id: "b", title: "test_user", role: "User" }),
          ]}
          environments={ENVS}
          appRoles={APP_ROLES}
          sessions={[
            { environment: "Production", role: "Admin" },
            { environment: "Production", role: "User" },
          ]}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).not.toBeDisabled();
    });

    it("renders the per-script role badge", () => {
      render(
        <JackInputSelection
          scripts={[makeEntry({ role: "Manager" })]}
          environments={ENVS}
          appRoles={APP_ROLES}
          sessions={SESSIONS}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByText("Manager")).toBeInTheDocument();
    });
  });

  describe("Confirm", () => {
    it("calls onConfirm with selected ids + run config", () => {
      const onConfirm = renderRunnable([makeEntry({ artifact_id: "abc-123" })]);
      fireEvent.click(screen.getByRole("button", { name: /Confirm & Run/i }));
      expect(onConfirm).toHaveBeenCalledWith(["abc-123"], {
        targetUrl: "https://app.example.com",
        environment: "Production",
        role: "Admin",
        browsers: ["chromium"],
      });
    });

    it("carries a multi-browser selection in the config", () => {
      const onConfirm = renderRunnable([makeEntry({ artifact_id: "id-1" })]);
      fireEvent.click(screen.getByRole("checkbox", { name: "Edge" }));
      fireEvent.click(screen.getByRole("button", { name: /Confirm & Run/i }));
      const config = onConfirm.mock.calls[0]![1];
      expect(config.browsers).toEqual(expect.arrayContaining(["chromium", "msedge"]));
    });

    it("disables Run when nothing is selected", () => {
      renderRunnable([makeEntry({ default_selected: false })]);
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).toBeDisabled();
    });

    it("disables Run when no browser is selected", () => {
      renderRunnable([makeEntry()]);
      fireEvent.click(screen.getByRole("checkbox", { name: "Chromium" }));
      expect(screen.getByRole("button", { name: /Confirm & Run/i })).toBeDisabled();
    });

    it("sends only the selected subset", () => {
      const onConfirm = renderRunnable([
        makeEntry({ artifact_id: "id-1", title: "test_login" }),
        makeEntry({ artifact_id: "id-2", title: "test_search", default_selected: true }),
      ]);
      fireEvent.click(screen.getByRole("checkbox", { name: "test_login" }));
      fireEvent.click(screen.getByRole("button", { name: /Confirm & Run/i }));
      expect(onConfirm.mock.calls[0]![0]).toEqual(["id-2"]);
    });
  });

  describe("Empty state", () => {
    it("renders empty-state message when scripts is empty", () => {
      render(<JackInputSelection scripts={[]} onConfirm={vi.fn()} />);
      expect(screen.getByText(/No scripts available/i)).toBeInTheDocument();
    });
  });
});
