import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ReviewContent } from "@/components/ReviewContent";
import { ExternalLink, Check, X, ChevronLeft, ChevronRight, AlertTriangle, MessageSquareX } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ExtractedPage } from "@/types/extraction";

interface SplitPanelProps {
  pages: ExtractedPage[];
  onApprove: (pageId: string, updatedMarkdown: string) => void;
  onSkip: (pageId: string) => void;
  onReject: (pageId: string, feedback: string) => void;
  disabled?: boolean;
  className?: string;
}

export function SplitPanel({
  pages,
  onApprove,
  onSkip,
  onReject,
  disabled,
  className,
}: SplitPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());
  const [markdownContent, setMarkdownContent] = useState("");
  const [activeTab, setActiveTab] = useState<"preview" | "edit">("preview");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");

  const totalPages = pages.length;
  const page = pages[currentIndex];

  // Reset local state when page changes
  useEffect(() => {
    if (page) {
      setMarkdownContent(page.requirement_md);
      setActiveTab("preview");
      setShowRejectInput(false);
      setRejectFeedback("");
    }
  }, [page]);

  // Clamp index when pages array shrinks
  useEffect(() => {
    if (currentIndex >= pages.length && pages.length > 0) {
      setCurrentIndex(pages.length - 1);
    }
  }, [pages.length, currentIndex]);

  if (!page) {
    return (
      <div className="p-4 text-center text-slate-500">No page selected.</div>
    );
  }

  const sourceLabel =
    page.source_type === "jira" ? "Open in Jira" : "Open Original";

  const qualityIssues = page.quality_issues ?? [];
  const rawWarnings = (page.warnings ?? []).filter(
    (w) =>
      !qualityIssues.some(
        (qi) => qi.category === "unsupported_content" && qi.message === w,
      ),
  );
  const hasWarnings = qualityIssues.length > 0 || rawWarnings.length > 0;

  function handleApprove() {
    const pid = page!.page_id;
    onApprove(pid, markdownContent);
    const next = new Set(resolvedIds);
    next.add(pid);
    setResolvedIds(next);
    // Auto-advance to next unresolved
    const nextIdx = pages.findIndex((p, i) => i > currentIndex && !next.has(p.page_id));
    if (nextIdx !== -1) {
      setCurrentIndex(nextIdx);
    }
  }

  function handleSkip() {
    const pid = page!.page_id;
    onSkip(pid);
    const next = new Set(resolvedIds);
    next.add(pid);
    setResolvedIds(next);
    const nextIdx = pages.findIndex((p, i) => i > currentIndex && !next.has(p.page_id));
    if (nextIdx !== -1) {
      setCurrentIndex(nextIdx);
    }
  }

  function handleRejectSubmit() {
    if (!rejectFeedback.trim()) return;
    onReject(page!.page_id, rejectFeedback.trim());
    setShowRejectInput(false);
    setRejectFeedback("");
  }

  return (
    <div
      className={cn(
        "flex flex-col h-[700px] border rounded-md overflow-hidden bg-white shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Review Requirement Page ({currentIndex + 1} of {totalPages}) —{" "}
          <span className="font-semibold">{page.page_title}</span>
          {resolvedIds.size > 0 && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              ({resolvedIds.size} resolved)
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <a
            href={page.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline flex items-center gap-1"
          >
            {sourceLabel} <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Navigation bar — only when more than one page */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-b bg-slate-50">
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
            {currentIndex + 1} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentIndex((i) => Math.min(totalPages - 1, i + 1))}
            disabled={currentIndex === totalPages - 1 || disabled}
            aria-label="Next item"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Warnings banner */}
      {hasWarnings && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-md mx-3 mt-3 p-3 overflow-y-auto max-h-32">
          <div className="flex items-center gap-2 mb-2 font-medium text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            Quality warnings detected
          </div>
          <div className="space-y-1">
            {qualityIssues.map((qi, i) => (
              <div key={i} className="text-xs">
                <Badge variant="outline" className="mr-1 text-amber-800 border-amber-400 bg-amber-100">
                  {qi.category}
                </Badge>
                {qi.message}
                {qi.impact && (
                  <span className="block ml-6 text-amber-600 mt-0.5">{qi.impact}</span>
                )}
              </div>
            ))}
            {rawWarnings.map((w, i) => (
              <div key={`rw-${i}`} className="text-xs">
                <Badge variant="outline" className="mr-1 text-amber-800 border-amber-400 bg-amber-100">
                  parser
                </Badge>
                {w}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Split layout */}
      <div className="flex flex-1 overflow-hidden mt-2">
        {/* Left Side: Source HTML */}
        <div className="w-1/2 border-r flex flex-col bg-slate-50">
          <div className="py-2 px-3 border-b text-xs font-medium text-slate-500 uppercase tracking-wider flex justify-between items-center bg-slate-100">
            <span>Raw Source (Read-only)</span>
          </div>
          <div className="flex-1 overflow-hidden bg-white">
            <iframe
              srcDoc={page.raw_html}
              className="w-full h-full border-none"
              sandbox=""
              title={`Source HTML for ${page.page_title}`}
            />
          </div>
        </div>

        {/* Right Side: Preview / Edit tabs */}
        <div className="w-1/2 flex flex-col bg-white">
          {/* Tab bar */}
          <div className="flex border-b bg-slate-100">
            <button
              className={cn(
                "px-4 py-2 text-xs font-medium uppercase tracking-wider transition-colors",
                activeTab === "preview"
                  ? "text-blue-700 border-b-2 border-blue-600 bg-white"
                  : "text-slate-500 hover:text-slate-700",
              )}
              onClick={() => setActiveTab("preview")}
            >
              Preview
            </button>
            <button
              className={cn(
                "px-4 py-2 text-xs font-medium uppercase tracking-wider transition-colors",
                activeTab === "edit"
                  ? "text-blue-700 border-b-2 border-blue-600 bg-white"
                  : "text-slate-500 hover:text-slate-700",
              )}
              onClick={() => setActiveTab("edit")}
            >
              Edit
            </button>
          </div>

          {activeTab === "preview" ? (
            <div className="flex-1 overflow-auto p-4">
              <ReviewContent content={markdownContent} />
            </div>
          ) : (
            <div className="flex-1 flex">
              <textarea
                className="w-full h-full p-4 resize-none border-none focus:outline-none focus:ring-0 font-mono text-sm text-slate-800 bg-slate-50"
                value={markdownContent}
                onChange={(e) => setMarkdownContent(e.target.value)}
                disabled={disabled}
              />
            </div>
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
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-block">
                <Button
                  variant="outline"
                  onClick={() => setShowRejectInput((v) => !v)}
                  disabled={disabled}
                  className="text-red-600 border-red-300 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <MessageSquareX className="w-4 h-4 mr-2" />
                  Reject
                </Button>
              </span>
            </TooltipTrigger>
            {disabled && (
              <TooltipContent side="top">
                <p>Review unavailable: please answer the active prompt first</p>
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
        <div className="flex items-center gap-3">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    variant="outline"
                    onClick={handleSkip}
                    disabled={disabled}
                    className="text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <X className="w-4 h-4 mr-2" />
                    Not requirement
                  </Button>
                </span>
              </TooltipTrigger>
              {disabled && (
                <TooltipContent side="top">
                  <p>Review unavailable: please answer the active prompt first</p>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    variant="default"
                    onClick={handleApprove}
                    disabled={disabled}
                    className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Approved
                  </Button>
                </span>
              </TooltipTrigger>
              {disabled && (
                <TooltipContent side="top">
                  <p>Review unavailable: please answer the active prompt first</p>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  );
}
