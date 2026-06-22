import { useState, useEffect, useRef } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Check,
  MessageSquareX,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  ExternalLink,
  SkipForward,
  XCircle,
  Edit2,
  Eye,
  UserCheck,
} from "lucide-react";
import type { ScriptReviewItem, ScriptValidationError } from "@/types/testcase";

// Must match react-syntax-highlighter's internal style type
const syntaxStyle: { [key: string]: CSSProperties } = vscDarkPlus;

// Client-side confidence thresholds (backend emits a float, no backend level for scripts)
function confidenceLevel(score: number): "high" | "medium" | "low" {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function ConfidenceBadge({ score }: { score: number }) {
  const level = confidenceLevel(score);
  const colorClass =
    level === "high"
      ? "bg-green-100 text-green-800 border-green-300"
      : level === "medium"
        ? "bg-amber-100 text-amber-800 border-amber-300"
        : "bg-red-100 text-red-800 border-red-300";
  const label = level.charAt(0).toUpperCase() + level.slice(1);
  return (
    <Badge variant="outline" className={cn("text-xs font-semibold", colorClass)}>
      {label} {score.toFixed(2)}
    </Badge>
  );
}

/** AC1 (13.7): format an ISO-8601 timestamp for display. Returns null when input is nullish. */
function formatApprovedAt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/** AC1 (13.7): renders "Approved by {user} · {timestamp}" caption when script is approved.
 *  Uses color + text (never color alone) per UX accessibility rules. */
function ApprovalCaption({
  approvedBy,
  approvedAt,
}: {
  approvedBy?: string | null;
  approvedAt?: string | null;
}) {
  const formatted = formatApprovedAt(approvedAt);
  if (!approvedBy && !formatted) return null;
  return (
    <div className="flex items-center gap-1 text-xs text-green-700 font-medium mt-1">
      <UserCheck className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
      <span>
        Approved{approvedBy ? ` by ${approvedBy}` : ""}
        {formatted ? ` · ${formatted}` : ""}
      </span>
    </div>
  );
}

interface SarahScriptReviewPanelProps {
  scripts: ScriptReviewItem[];
  /** Called when the user approves a script. editedContent is present when
   *  the user modified the script in the Edit pane; undefined means "no edit,
   *  save the original" (back-compat path for 13.5). */
  onApprove: (index: number, editedContent?: string) => void;
  onReject: (index: number, feedback: string) => void;
  onSkip: (index: number) => void;
  /** Per-script validation errors set by App.tsx on a script_validation_error message. */
  validationErrors?: Record<number, ScriptValidationError[]>;
  disabled?: boolean;
  className?: string;
}

export function SarahScriptReviewPanel({
  scripts,
  onApprove,
  onReject,
  onSkip,
  validationErrors,
  disabled,
  className,
}: SarahScriptReviewPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [resolvedIndices, setResolvedIndices] = useState<Set<number>>(new Set());
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");

  // 13.6 — per-script edit buffer (AC1: retained across Prev/Next, reset on new payload)
  const [edits, setEdits] = useState<Record<number, string>>({});
  // 13.6 — Preview vs Edit tab for the right (script) pane
  const [activeTab, setActiveTab] = useState<"preview" | "edit">("preview");

  const total = scripts.length;
  const item = scripts[currentIndex]!;

  // Track the previous scripts payload so we can prune stale edits when a new one arrives.
  const scriptsRef = useRef(scripts);

  // Prune the edit buffer when a new script_review payload arrives.
  // The backend re-presents the FULL list after every approve/skip (a new array
  // object each time), so wiping on object identity alone would destroy unsaved
  // edits for not-yet-resolved scripts. Instead, drop only the edit slots whose
  // underlying script_content actually changed (a genuine regeneration of that
  // script); edits for scripts the server left untouched survive a sibling approve.
  useEffect(() => {
    const prev = scriptsRef.current;
    if (prev === scripts) return;
    scriptsRef.current = scripts;

    const kept: Record<number, string> = {};
    let prunedAny = false;
    for (const key of Object.keys(edits)) {
      const idx = Number(key);
      // Keep the edit only if the script at this index still has the same
      // content the user was editing against; otherwise it was regenerated.
      if (scripts[idx]?.script_content === prev[idx]?.script_content) {
        kept[idx] = edits[idx]!;
      } else {
        prunedAny = true;
      }
    }
    if (prunedAny) {
      setEdits(kept);
      // Only snap back to Preview on a genuine regeneration that dropped an
      // edit; a plain sibling re-present must not yank the user out of Edit.
      setActiveTab("preview");
    }
  }, [scripts, edits]);

  // Clamp index when array shrinks after a rejection+regeneration
  useEffect(() => {
    if (currentIndex >= scripts.length && scripts.length > 0) {
      setCurrentIndex(scripts.length - 1);
    }
  }, [scripts.length, currentIndex]);

  // Reset feedback when navigating
  useEffect(() => {
    setShowRejectInput(false);
    setRejectFeedback("");
  }, [currentIndex]);

  // Sync resolved set from server-emitted status
  useEffect(() => {
    const synced = new Set<number>();
    scripts.forEach((s) => {
      if (s.status !== "pending") synced.add(s.index);
    });
    setResolvedIndices(synced);
  }, [scripts]);

  // Derived: is the current script edited (dirty)?
  const currentEdit = edits[currentIndex];
  const isDirty =
    currentEdit !== undefined && currentEdit !== item.script_content;

  // Current validation errors for this script (cleared by App.tsx on new script_review)
  const currentErrors = validationErrors?.[currentIndex] ?? [];
  const hasValidationErrors = currentErrors.length > 0;

  function handleApprove() {
    // AC3: pass the edited content when dirty; undefined triggers back-compat path
    onApprove(item.index, isDirty ? currentEdit : undefined);
    const next = new Set(resolvedIndices);
    next.add(currentIndex);
    setResolvedIndices(next);
    const nextIdx = scripts.findIndex((_, i) => i > currentIndex && !next.has(i));
    if (nextIdx !== -1) setCurrentIndex(nextIdx);
  }

  function handleSkip() {
    onSkip(item.index);
    const next = new Set(resolvedIndices);
    next.add(currentIndex);
    setResolvedIndices(next);
    const nextIdx = scripts.findIndex((_, i) => i > currentIndex && !next.has(i));
    if (nextIdx !== -1) setCurrentIndex(nextIdx);
  }

  function handleRejectSubmit() {
    if (!rejectFeedback.trim()) return;
    onReject(item.index, rejectFeedback.trim());
    const next = new Set(resolvedIndices);
    next.delete(currentIndex);
    setResolvedIndices(next);
    setShowRejectInput(false);
    setRejectFeedback("");
  }

  if (!item) {
    return <div className="p-4 text-center text-slate-500">No scripts to review.</div>;
  }

  const tc = item.test_case;
  const hasWarnings = (item.warnings?.length ?? 0) > 0;
  const isFailed = !!item.error_message;

  return (
    <div
      className={cn(
        "flex flex-col border rounded-md overflow-hidden bg-white shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Review Script ({currentIndex + 1} of {total}) —{" "}
          <span className="font-semibold">{tc.title}</span>
          {resolvedIndices.size > 0 && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              ({resolvedIndices.size} of {total} reviewed)
            </span>
          )}
          {/* AC1 (13.7): approval caption — color + text, visible when this script is approved */}
          {item.status === "approved" && (
            <ApprovalCaption approvedBy={item.approved_by} approvedAt={item.approved_at} />
          )}
        </div>
        <ConfidenceBadge score={item.confidence} />
      </div>

      {/* Per-item status strip */}
      {total > 1 && (
        <div className="flex items-center gap-1 px-4 pt-2">
          {scripts.map((s, i) => {
            const statusClass =
              s.status === "approved"
                ? "bg-green-500"
                : s.status === "skipped"
                  ? "bg-slate-400"
                  : "bg-slate-200";
            const label =
              s.status === "approved"
                ? "Approved"
                : s.status === "skipped"
                  ? "Skipped"
                  : "Pending";
            return (
              <button
                key={i}
                onClick={() => setCurrentIndex(i)}
                title={`${i + 1}: ${s.test_case.title} — ${label}`}
                aria-label={`Script ${i + 1}: ${label}`}
                className={cn(
                  "w-4 h-4 rounded-full border-2 transition-all",
                  statusClass,
                  i === currentIndex ? "border-slate-700 scale-125" : "border-transparent",
                )}
              />
            );
          })}
        </div>
      )}

      {/* Navigation bar */}
      {total > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-b bg-slate-50 mt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
            disabled={currentIndex === 0 || disabled}
            aria-label="Previous script"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </Button>
          <span className="text-xs text-slate-500">{currentIndex + 1} / {total}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentIndex((i) => Math.min(total - 1, i + 1))}
            disabled={currentIndex === total - 1 || disabled}
            aria-label="Next script"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Warnings banner (AC3: advisory, non-blocking — script pane always visible) */}
      {hasWarnings && (
        <div className="mx-3 mt-3 bg-amber-50 border border-amber-200 rounded-md p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-800 mb-1">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            Review warnings ({item.warnings!.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {item.warnings!.map((w, i) => (
              <Badge key={i} variant="outline" className="text-xs text-amber-700 border-amber-300">
                {w}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* 13.6 — Validation error banner (AC2): red, distinct from amber warnings banner.
          Errors do not hide the script pane — the user can still see and fix their code. */}
      {hasValidationErrors && (
        <div
          className="mx-3 mt-3 bg-red-50 border border-red-200 rounded-md p-3"
          role="alert"
          aria-label="Validation errors"
        >
          <div className="flex items-center gap-2 text-sm font-medium text-red-800 mb-1">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            Validation errors — fix the issues below and approve again
          </div>
          <ul className="space-y-0.5">
            {currentErrors.map((err, i) => (
              <li key={i} className="text-xs text-red-700">
                {err.line != null ? <strong>Line {err.line}:</strong> : null}{" "}
                {err.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Error banner for failed-generation placeholder */}
      {isFailed && (
        <div className="mx-3 mt-3 bg-red-50 border border-red-200 rounded-md p-3 flex items-start gap-2">
          <XCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-red-700">Generation failed</div>
            <div className="text-xs text-red-600 mt-0.5">{item.error_message}</div>
          </div>
        </div>
      )}

      {/* Side-by-side body (AC1) */}
      <div className="flex-1 grid grid-cols-2 min-h-[400px] divide-x overflow-hidden">
        {/* Left: structured test case */}
        <div className="overflow-auto p-4 space-y-4">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Source Test Case
          </div>

          {tc.objective && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                Objective
              </div>
              <p className="text-sm text-slate-700">{tc.objective}</p>
            </div>
          )}

          {tc.source_requirement_name && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                Source Requirement
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-700">
                <span>{tc.source_requirement_name}</span>
                {tc.source_url && (
                  <a
                    href={tc.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                  >
                    Open <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          )}

          {tc.preconditions.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                Preconditions
              </div>
              <ol className="list-decimal list-inside text-sm text-slate-700 space-y-0.5">
                {tc.preconditions.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            </div>
          )}

          {tc.steps.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                Steps
              </div>
              <ol className="text-sm text-slate-700 space-y-1">
                {tc.steps.map((s) => (
                  <li key={s.number} className="flex gap-2">
                    <span className="font-medium text-slate-500 min-w-[1.5rem]">{s.number}.</span>
                    <span>
                      {s.action}{" "}
                      <span className="text-xs text-slate-400">(target: {s.target})</span>
                      {s.data && (
                        <span className="ml-1 text-xs text-slate-500">— Data: {s.data}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {tc.expected_results.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                Expected Results
              </div>
              <ol className="list-decimal list-inside text-sm text-slate-700 space-y-0.5">
                {tc.expected_results.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* Right: script pane with Preview/Edit tabs (13.6) */}
        <div
          role="region"
          className="flex flex-col overflow-hidden bg-[#1e1e1e]"
          aria-label="Generated Playwright script"
        >
          {/* Tab bar */}
          <div className="flex items-center border-b border-[#3c3c3c] bg-[#2d2d2d] px-2 pt-1 gap-1">
            <button
              onClick={() => setActiveTab("preview")}
              className={cn(
                "flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-t transition-colors",
                activeTab === "preview"
                  ? "bg-[#1e1e1e] text-slate-100 border border-b-0 border-[#3c3c3c]"
                  : "text-slate-400 hover:text-slate-200",
              )}
              aria-label="Preview tab"
            >
              <Eye className="w-3 h-3" />
              Preview
            </button>
            <button
              onClick={() => setActiveTab("edit")}
              className={cn(
                "flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-t transition-colors",
                activeTab === "edit"
                  ? "bg-[#1e1e1e] text-slate-100 border border-b-0 border-[#3c3c3c]"
                  : "text-slate-400 hover:text-slate-200",
              )}
              aria-label="Edit tab"
            >
              <Edit2 className="w-3 h-3" />
              Edit
              {/* Dot indicator when this pane has unsaved edits */}
              {isDirty && (
                <span
                  className="w-1.5 h-1.5 rounded-full bg-amber-400"
                  aria-hidden="true"
                />
              )}
            </button>

            {/* 13.6 AC1 — unsaved-changes indicator: color + text (not color alone) */}
            {isDirty && (
              <Badge
                variant="outline"
                className="ml-auto text-xs text-amber-700 border-amber-400 bg-amber-950/30"
                aria-label="Unsaved changes"
              >
                ● Unsaved changes
              </Badge>
            )}
          </div>

          {/* Preview pane */}
          {activeTab === "preview" && (
            <div className="flex-1 overflow-auto text-sm font-mono">
              <SyntaxHighlighter
                style={syntaxStyle}
                language="python"
                PreTag="div"
                wrapLongLines
                customStyle={{
                  margin: 0,
                  background: "transparent",
                  padding: "1rem",
                  fontSize: "0.75rem",
                }}
              >
                {item.script_content}
              </SyntaxHighlighter>
            </div>
          )}

          {/* Edit pane — plain font-mono textarea (no new editor package) */}
          {activeTab === "edit" && (
            <textarea
              className="flex-1 w-full bg-[#1e1e1e] text-slate-100 font-mono text-xs p-4 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={currentEdit ?? item.script_content}
              onChange={(e) =>
                setEdits((prev) => ({ ...prev, [currentIndex]: e.target.value }))
              }
              disabled={disabled}
              aria-label="Edit script content"
              spellCheck={false}
            />
          )}
        </div>
      </div>

      {/* Reject feedback input */}
      {showRejectInput && (
        <div className="px-4 py-3 border-t bg-slate-50">
          <div className="text-xs text-slate-600 mb-1 font-medium">
            Describe what needs to be changed:
          </div>
          <textarea
            className="w-full border rounded-md p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-400 text-slate-800 bg-white"
            rows={3}
            placeholder="Describe what needs to be changed…"
            maxLength={1000}
            value={rejectFeedback}
            onChange={(e) => setRejectFeedback(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (rejectFeedback.trim() && !disabled) handleRejectSubmit();
              }
            }}
            disabled={disabled}
          />
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-slate-400">{rejectFeedback.length}/1000</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowRejectInput(false);
                  setRejectFeedback("");
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="bg-red-600 hover:bg-red-700 text-white"
                onClick={handleRejectSubmit}
                disabled={!rejectFeedback.trim() || disabled}
              >
                Submit Feedback
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Footer (AC2, AC3) */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 bg-slate-50 border-t">
        <Button
          variant="outline"
          onClick={() => setShowRejectInput((v) => !v)}
          disabled={disabled}
          className="text-red-600 border-red-300 hover:bg-red-50"
        >
          <MessageSquareX className="w-4 h-4 mr-2" />
          Reject
        </Button>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSkip}
            disabled={disabled}
            className="text-slate-600"
          >
            <SkipForward className="w-4 h-4 mr-1" />
            Skip
          </Button>
          <Button
            variant="default"
            onClick={handleApprove}
            disabled={disabled}
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Check className="w-4 h-4 mr-2" />
            Approve
          </Button>
        </div>
      </div>
    </div>
  );
}
