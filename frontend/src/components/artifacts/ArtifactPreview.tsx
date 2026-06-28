import { useEffect, useState } from "react";
import { X, FileText, Pencil, Trash2, Download } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { CSSProperties } from "react";
import { apiFetch, API_BASE_PATH } from "@/lib/api";
import { updateArtifactContent, deleteArtifact } from "@/lib/artifacts";
import { ReviewContent } from "@/components/ReviewContent";
import { MermaidDiagram } from "@/components/artifacts/MermaidDiagram";
import type { Artifact } from "@/components/conversations/ProjectSidebar";
import { useFocusTrap } from "@/lib/useFocusTrap";

// Type for SyntaxHighlighter style (matches react-syntax-highlighter internals)
const syntaxHighlighterStyle: { [key: string]: CSSProperties } = vscDarkPlus;

interface ArtifactPreviewProps {
  artifact: Artifact;
  onClose: () => void;
  onSelfMutation?: (type: "updated" | "deleted") => void;
}

interface ArtifactContent {
  artifact_id: string;
  version: number;
  content: string;
  content_encoding: "text" | "base64";
}

// D3: Infer MIME type from file extension for image rendering.
function mimeFromName(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    svg: "image/svg+xml",
    webp: "image/webp",
  };
  return map[ext] ?? "application/octet-stream";
}

// D2: Infer syntax-highlight language from file extension.
function languageFromName(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    py: "python",
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
  };
  return map[ext] ?? "text";
}

export function ArtifactPreview({ artifact, onClose, onSelfMutation }: ArtifactPreviewProps) {
  const [content, setContent] = useState<string | null>(null);
  const [contentEncoding, setContentEncoding] = useState<"text" | "base64">("text");
  const [version, setVersion] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit/Delete State
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Focus traps for a11y (Story 16.6)
  const previewRef = useFocusTrap(true, onClose);
  const deleteTrapRef = useFocusTrap(isConfirmingDelete, () => setIsConfirmingDelete(false));

  // Binary report artifacts (Playwright trace.zip / video) are large and not previewable as
  // text — skip the 1 MB /content fetch and offer a direct download instead.
  const downloadOnly = artifact.kind === "trace" || artifact.kind === "video";
  const downloadUrl = `${API_BASE_PATH}/projects/${artifact.project_id}/artifacts/${artifact.id}/download`;

  useEffect(() => {
    let cancelled = false;

    if (downloadOnly) {
      setContent(""); // sentinel: lets renderBody show the download UI without a /content call
      setContentEncoding("base64");
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    setContent(null);

    apiFetch<ArtifactContent>(
      `/projects/${artifact.project_id}/artifacts/${artifact.id}/content`,
    )
      .then((data) => {
        if (cancelled) return;
        setContent(data.content);
        setContentEncoding(data.content_encoding);
        setVersion(data.version);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load artifact content");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [artifact.project_id, artifact.id, downloadOnly]);

  // AC4 — creator/updater + updated-at for the header subtitle
  const updatedAt = artifact.updated_at
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "numeric",
      }).format(new Date(artifact.updated_at))
    : null;

  const isEditable = !["image", "screenshot", "trace", "video", "execution_screenshot"].includes(
    artifact.kind,
  );

  function handleEditClick() {
    setEditValue(content || "");
    setIsEditing(true);
  }

  async function handleSave() {
    setIsSaving(true);
    setError(null);
    try {
      // Returns the updated Artifact with new version, but we only strictly need the version bump.
      // Wait, updateArtifactContent doesn't return version. We can just refetch, or optimistically bump.
      // Wait, `/versions` returns ArtifactResponse. But Artifact doesn't expose version in TS.
      // We will just optimistically bump it here.
      await updateArtifactContent(artifact.project_id, artifact.id, editValue, "text");
      onSelfMutation?.("updated");
      setContent(editValue);
      setVersion((v) => (v ? v + 1 : 1));
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save artifact");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete() {
    setIsDeleting(true);
    setError(null);
    try {
      await deleteArtifact(artifact.project_id, artifact.id);
      onSelfMutation?.("deleted");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete artifact");
      setIsDeleting(false);
      setIsConfirmingDelete(false);
    }
  }

  // Render the content body based on kind + content_encoding (Task 2.2)
  function renderBody() {
    if (content === null) return null;

    if (isEditing) {
      return (
        <div className="flex flex-col h-full bg-[#1e1e1e] rounded-md border border-[#374151] overflow-hidden">
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            disabled={isSaving}
            className="flex-1 w-full bg-transparent text-[#d4d4d4] font-mono text-sm p-4 outline-none resize-none disabled:opacity-50"
            spellCheck={false}
          />
        </div>
      );
    }

    const kind = artifact.kind;

    // Playwright trace — not previewable; offer download + how to open it.
    if (kind === "trace") {
      return (
        <div className="flex flex-col gap-3 text-sm text-[#334155]">
          <p>
            Playwright trace — a full step-by-step replay of the run (DOM snapshots, network,
            console, timeline).
          </p>
          <a
            href={downloadUrl}
            className="inline-flex w-fit items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700"
          >
            <Download className="w-4 h-4" />
            Download trace.zip
          </a>
          <p className="text-xs text-[#64748b]">
            Open it in the Playwright Trace Viewer: drop the file onto{" "}
            <span className="font-mono">trace.playwright.dev</span>, or run{" "}
            <span className="font-mono">npx playwright show-trace &lt;file&gt;</span>.
          </p>
        </div>
      );
    }

    // Playwright video → inline player (streamed from the download endpoint, no 1 MB cap).
    if (kind === "video") {
      return (
        <div className="flex flex-col gap-3">
          <video
            controls
            src={downloadUrl}
            className="max-w-full rounded border border-[#e2e8f0]"
          />
          <a href={downloadUrl} className="text-sm text-indigo-600 hover:underline w-fit">
            Download video
          </a>
        </div>
      );
    }

    // Execution screenshot (.png, base64) → inline image.
    if (kind === "execution_screenshot" && contentEncoding === "base64") {
      const mime = mimeFromName(artifact.name);
      if (mime !== "application/octet-stream") {
        return (
          <img
            src={`data:${mime};base64,${content}`}
            alt={artifact.name}
            className="max-w-full h-auto rounded"
          />
        );
      }
    }

    // Image / screenshot with base64 encoding → <img data:…>
    if ((kind === "image" || kind === "screenshot") && contentEncoding === "base64") {
      const mime = mimeFromName(artifact.name);
      if (mime === "application/octet-stream") {
        return (
          <div className="text-sm text-slate-500 italic py-4">
            Cannot preview this image format.
          </div>
        );
      }
      return (
        <img
          src={`data:${mime};base64,${content}`}
          alt={artifact.name}
          className="max-w-full h-auto rounded"
        />
      );
    }

    // Mermaid diagram → MermaidDiagram (D1, Task 3.3)
    if (kind === "mermaid") {
      return <MermaidDiagram chart={content} />;
    }

    // Script kinds → syntax-highlighted code (D2, Task 2.2)
    // Do NOT fence-wrap — raw content rendered directly to avoid backtick breakage.
    if (kind === "playwright_script" || kind === "testscript") {
      const lang = languageFromName(artifact.name);
      return (
        <SyntaxHighlighter
          style={syntaxHighlighterStyle}
          language={lang}
          PreTag="div"
          className="rounded-md text-xs"
          wrapLongLines
        >
          {content}
        </SyntaxHighlighter>
      );
    }

    // All other text kinds (requirements, report, markdown, testcase, raw_html, etc.)
    // → ReviewContent Markdown path.  raw_html rendered as text (no dangerouslySetInnerHTML — XSS).
    return <ReviewContent content={content} className="max-h-none" />;
  }

  return (
    <div ref={previewRef as any} tabIndex={-1} className="flex-1 flex flex-col overflow-hidden bg-white outline-none">
      {/* Header — FROZEN: h3 name node + Close preview aria-label must remain unchanged */}
      <div className="px-5 py-3.5 border-b border-[#e2e8f0] flex items-center gap-3 bg-white flex-shrink-0">
        <div className="w-9 h-9 rounded-full flex items-center justify-center bg-[#f1f5f9] text-[#64748b] flex-shrink-0">
          <FileText className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-[15px] font-semibold text-[#0f172a] leading-tight truncate">
            {artifact.name}
          </h3>
          <div className="text-xs text-[#64748b] mt-0.5">
            {artifact.kind}
            {version !== null && ` · v${version}`}
          </div>
          {/* AC2 / D4: creator/updater from Artifact prop (10-2); omit when null */}
          <div className="text-xs text-[#94a3b8] mt-0.5 space-y-0.5">
            {artifact.created_by_display && (
              <div>created by {artifact.created_by_display}</div>
            )}
            {(updatedAt || artifact.updated_by_display) && (
              <div>
                updated
                {updatedAt && ` ${updatedAt}`}
                {artifact.updated_by_display && ` by ${artifact.updated_by_display}`}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isConfirmingDelete ? (
            <div ref={deleteTrapRef as any} tabIndex={-1} className="flex items-center bg-[#fee2e2] rounded-md px-2 py-1 mr-2 text-xs outline-none">
              <span className="text-[#ef4444] font-medium mr-3">Delete artifact?</span>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="text-[#ef4444] font-bold hover:underline disabled:opacity-50 mr-3"
              >
                {isDeleting ? "Deleting..." : "Confirm"}
              </button>
              <button
                onClick={() => setIsConfirmingDelete(false)}
                disabled={isDeleting}
                className="text-[#991b1b] hover:underline disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          ) : isEditing ? (
            <div className="flex items-center mr-2 text-xs">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="bg-[#3b82f6] text-white px-3 py-1.5 rounded hover:bg-[#2563eb] transition-colors disabled:opacity-50 font-medium mr-2"
              >
                {isSaving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => setIsEditing(false)}
                disabled={isSaving}
                className="px-3 py-1.5 text-[#64748b] hover:bg-[#f1f5f9] rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <>
              <a
                href={downloadUrl}
                className="p-1.5 text-[#64748b] hover:bg-[#f1f5f9] rounded-md transition-colors inline-flex"
                aria-label="Download artifact"
                title="Download artifact"
              >
                <Download className="w-4 h-4" />
              </a>
              {isEditable && (
                <button
                  onClick={handleEditClick}
                  className="p-1.5 text-[#64748b] hover:bg-[#f1f5f9] rounded-md transition-colors"
                  aria-label="Edit artifact"
                  title="Edit artifact"
                >
                  <Pencil className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => setIsConfirmingDelete(true)}
                className="p-1.5 text-[#ef4444] hover:bg-[#fee2e2] rounded-md transition-colors"
                aria-label="Delete artifact"
                title="Delete artifact"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}

          {!isEditing && (
            <button
              onClick={onClose}
              className="p-1.5 text-[#64748b] hover:bg-[#f1f5f9] rounded-md transition-colors border-l border-[#e2e8f0] ml-1"
              aria-label="Close preview"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {isLoading && (
          <div className="flex items-center justify-center py-12 text-[#64748b] text-sm">
            Loading artifact content…
          </div>
        )}
        {error && (
          <div className="bg-[#fee2e2] text-[#ef4444] px-4 py-3 rounded text-sm border border-[#f87171]/20">
            {error}
          </div>
        )}
        {content !== null && !isLoading && renderBody()}
      </div>
    </div>
  );
}
