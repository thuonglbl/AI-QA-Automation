import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Check,
  MessageSquareX,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { ReviewContent } from "@/components/ReviewContent";
import type { MaryReviewCase, ConfidenceLevel } from "@/types/testcase";

interface MaryReviewPanelProps {
  testCases: MaryReviewCase[];
  onApprove: (index: number) => void;
  onReject: (index: number, feedback: string) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Drop a leading "# Title" line from the test-case Markdown: the panel header already
 * shows the title, so rendering it again as an H1 would duplicate it.
 */
function bodyMarkdown(markdown: string): string {
  return markdown.replace(/^\s*#\s+.*(?:\r?\n)+/, "");
}

function ConfidenceBadge({
  level,
  score,
  rationale,
  warnings,
}: {
  level: ConfidenceLevel | null | undefined;
  score: number | null | undefined;
  rationale?: string[];
  warnings?: string[];
}) {
  const [open, setOpen] = useState(false);

  if (!level) return null;

  const colorClass =
    level === "high"
      ? "bg-green-100 text-green-800 border-green-300"
      : level === "medium"
        ? "bg-amber-100 text-amber-800 border-amber-300"
        : "bg-red-100 text-red-800 border-red-300";

  const scoreStr = score != null ? score.toFixed(2) : "?";
  const causes = [...(rationale ?? []), ...(warnings ?? [])];

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={cn("text-xs font-semibold", colorClass)}>
          {level.toUpperCase()}
        </Badge>
        <span className="text-xs text-slate-500">score: {scoreStr}</span>
        {causes.length > 0 && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
            aria-label="Toggle confidence rationale"
          >
            Why this score
            {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>
      {open && causes.length > 0 && (
        <ul className="mt-2 ml-2 space-y-1 text-xs text-slate-600">
          {causes.map((c, i) => (
            <li key={i} className="flex gap-1">
              <span className="text-slate-400">•</span>
              {c}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MaryReviewPanel({
  testCases,
  onApprove,
  onReject,
  disabled,
  className,
}: MaryReviewPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [resolvedIndices, setResolvedIndices] = useState<Set<number>>(new Set());
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");

  const total = testCases.length;
  const tc = testCases[currentIndex]!;

  // Clamp index when array shrinks after a rejection+regeneration
  useEffect(() => {
    if (currentIndex >= testCases.length && testCases.length > 0) {
      setCurrentIndex(testCases.length - 1);
    }
  }, [testCases.length, currentIndex]);

  // Reset feedback input when navigating
  useEffect(() => {
    setShowRejectInput(false);
    setRejectFeedback("");
  }, [currentIndex]);

  // Sync resolved set from server-authoritative approval status. A reject
  // re-emits a fresh testCases array (remount), so rebuild resolved/nav state
  // from approved_at rather than relying on the local set surviving the remount.
  useEffect(() => {
    const synced = new Set<number>();
    testCases.forEach((c, i) => {
      if (c.approved_at != null) synced.add(i);
    });
    setResolvedIndices(synced);
  }, [testCases]);

  const lowConfidenceCount = testCases.filter((c) => c.confidence_level === "low").length;

  function handleApprove() {
    onApprove(currentIndex);
    const next = new Set(resolvedIndices);
    next.add(currentIndex);
    setResolvedIndices(next);
    // Auto-advance to first unresolved case
    const nextIdx = testCases.findIndex((_, i) => i > currentIndex && !next.has(i));
    if (nextIdx !== -1) {
      setCurrentIndex(nextIdx);
    }
  }

  function handleRejectSubmit() {
    if (!rejectFeedback.trim()) return;
    onReject(currentIndex, rejectFeedback.trim());
    // Clear the resolved status for this index (regeneration = new decision needed)
    const next = new Set(resolvedIndices);
    next.delete(currentIndex);
    setResolvedIndices(next);
    setShowRejectInput(false);
    setRejectFeedback("");
  }

  if (!tc) {
    return (
      <div className="p-4 text-center text-slate-500">No test case selected.</div>
    );
  }

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
          Review Test Case ({currentIndex + 1} of {total}) —{" "}
          <span className="font-semibold">{tc.title}</span>
          {resolvedIndices.size > 0 && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              ({resolvedIndices.size} resolved)
            </span>
          )}
        </div>
      </div>

      {/* Low-confidence summary banner */}
      {lowConfidenceCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-md mx-3 mt-3 p-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {lowConfidenceCount} of {total} test{" "}
            {lowConfidenceCount === 1 ? "case is" : "cases are"} low confidence — review each
            before proceeding.
          </div>
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
            aria-label="Previous item"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </Button>
          <span className="text-xs text-slate-500">
            {currentIndex + 1} / {total}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentIndex((i) => Math.min(total - 1, i + 1))}
            disabled={currentIndex === total - 1 || disabled}
            aria-label="Next item"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Test case body — rendered as Markdown (the same document stored + fed to the LLM) */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Confidence badge (review-only metadata, kept outside the Markdown document) */}
        <ConfidenceBadge
          level={tc.confidence_level}
          score={tc.confidence}
          rationale={tc.confidence_rationale}
          warnings={tc.warnings}
        />

        <ReviewContent content={bodyMarkdown(tc.markdown)} className="max-h-none" />
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

      {/* Footer Buttons */}
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
  );
}
