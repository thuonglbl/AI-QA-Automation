/**
 * Story 10-3 (Task 6.2): Focused Vitest coverage for ArtifactPreview.
 *
 * Tests:
 * - Renders <img data:…> for image/screenshot artifact with content_encoding: "base64"
 * - Renders Markdown for markdown/requirements artifact via ReviewContent
 * - Shows creator/updater when *_display fields are present
 * - Omits gracefully when *_display is null
 * - Shows loading state initially
 * - Shows error on fetch failure
 *
 * Mock strategy:
 * - apiFetch is mocked (no network hits)
 * - MermaidDiagram is mocked (already tested separately)
 * - Matches existing test style (describe/it/expect/vi, @testing-library/react)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ArtifactPreview } from "../artifacts/ArtifactPreview";
import type { Artifact } from "../conversations/ProjectSidebar";

// Mock apiFetch to avoid network calls
vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

// Mock MermaidDiagram to avoid mermaid library initialization in tests
vi.mock("../artifacts/MermaidDiagram", () => ({
  MermaidDiagram: ({ chart }: { chart: string }) => (
    <div data-testid="mermaid-diagram">{chart}</div>
  ),
}));

import { apiFetch } from "@/lib/api";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

function makeArtifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: "artifact-123",
    project_id: "project-456",
    kind: "markdown",
    name: "test.md",
    created_at: "2026-06-11T00:00:00Z",
    updated_at: "2026-06-11T12:00:00Z",
    created_by_user_id: "user-1",
    updated_by_user_id: "user-2",
    created_by_display: null,
    updated_by_display: null,
    ...overrides,
  };
}

describe("ArtifactPreview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    // Never resolve — stay in loading state
    mockApiFetch.mockReturnValue(new Promise(() => {}));

    render(
      <ArtifactPreview
        artifact={makeArtifact()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/Loading artifact content/i)).toBeInTheDocument();
  });

  it("renders Markdown content for a 'markdown' artifact via ReviewContent", async () => {
    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: "# Hello World",
      content_encoding: "text",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({ kind: "markdown", name: "doc.md" })}
        onClose={vi.fn()}
      />,
    );

    // Should eventually render the Markdown heading
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Hello World" })).toBeInTheDocument();
    });
  });

  it("renders Markdown content for a 'requirements' artifact", async () => {
    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: "# Requirements\n\nSome content.",
      content_encoding: "text",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({ kind: "requirements", name: "req.md" })}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Requirements" })).toBeInTheDocument();
    });
  });

  it("renders <img data:...> for an 'image' artifact with base64 encoding", async () => {
    const base64Content = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: base64Content,
      content_encoding: "base64",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({ kind: "image", name: "photo.png" })}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      const img = screen.getByRole("img", { name: "photo.png" });
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", `data:image/png;base64,${base64Content}`);
    });
  });

  it("renders <img data:...> for a 'screenshot' artifact with base64 encoding", async () => {
    const base64Content = "abc123==";

    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: base64Content,
      content_encoding: "base64",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({ kind: "screenshot", name: "screen.jpg" })}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      const img = screen.getByRole("img", { name: "screen.jpg" });
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", `data:image/jpeg;base64,${base64Content}`);
    });
  });

  it("shows creator/updater when *_display fields are present (AC2)", async () => {
    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 2,
      content: "# Spec",
      content_encoding: "text",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({
          kind: "requirements",
          name: "spec.md",
          created_by_display: "Alice",
          updated_by_display: "Bob",
        })}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/created by Alice/i)).toBeInTheDocument();
      expect(screen.getByText(/updated.*by Bob/i)).toBeInTheDocument();
    });
  });

  it("omits creator/updater gracefully when *_display is null (D4)", async () => {
    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: "# Spec",
      content_encoding: "text",
    });

    const { container } = render(
      <ArtifactPreview
        artifact={makeArtifact({
          kind: "requirements",
          name: "spec.md",
          created_by_display: null,
          updated_by_display: null,
        })}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText(/created by/i)).not.toBeInTheDocument();
    });

    // Also verify no UUID or "undefined" is rendered
    const text = container.textContent ?? "";
    expect(text).not.toContain("undefined");
    expect(text).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  });

  it("shows error when content fetch fails", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("Network error"));

    render(
      <ArtifactPreview
        artifact={makeArtifact()}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });
  });

  it("renders the artifact name in the h3 header (frozen contract)", async () => {
    mockApiFetch.mockResolvedValueOnce({
      artifact_id: "artifact-123",
      version: 1,
      content: "content",
      content_encoding: "text",
    });

    render(
      <ArtifactPreview
        artifact={makeArtifact({ name: "my-artifact.md" })}
        onClose={vi.fn()}
      />,
    );

    // The h3 heading with the artifact name must be present (frozen — 10-7/10-8 rely on it)
    expect(screen.getByRole("heading", { name: "my-artifact.md" })).toBeInTheDocument();
  });

  it("renders the Close preview button with correct aria-label (frozen contract)", () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}));

    render(
      <ArtifactPreview
        artifact={makeArtifact()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Close preview" }),
    ).toBeInTheDocument();
  });

  it("calls onClose when Close preview is clicked", async () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}));
    const onClose = vi.fn();

    render(
      <ArtifactPreview artifact={makeArtifact()} onClose={onClose} />,
    );

    screen.getByRole("button", { name: "Close preview" }).click();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
