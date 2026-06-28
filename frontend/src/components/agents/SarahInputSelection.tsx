import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import type { TestCaseInput, ConfidenceLevel } from "@/types/testcase";

interface SarahInputSelectionProps {
  testCases: TestCaseInput[];
  onConfirm: (selectedIds: string[]) => void;
  /** Called when the user confirms with NOTHING selected — skip script generation and
   *  hand off straight to Jack, which reuses existing approved scripts. */
  onSkip?: () => void;
  disabled?: boolean;
}

function ConfidenceBadge({ level }: { level: ConfidenceLevel | null | undefined }) {
  if (!level) return null;
  const colorClass =
    level === "high"
      ? "bg-green-100 text-green-800 border-green-300"
      : level === "medium"
        ? "bg-amber-100 text-amber-800 border-amber-300"
        : "bg-red-100 text-red-800 border-red-300";
  return (
    <Badge variant="outline" className={cn("text-xs font-semibold ml-1", colorClass)}>
      {level.toUpperCase()}
    </Badge>
  );
}

function TestCaseRow({
  entry,
  checked,
  onToggle,
}: {
  entry: TestCaseInput;
  checked: boolean;
  onToggle: (id: string) => void;
}) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const hasSource = !!entry.source_url;
  const hasPreview = !!entry.preview;

  return (
    <div
      className={cn(
        "border rounded-md px-4 py-3 flex flex-col gap-2 transition-colors",
        checked ? "border-purple-300 bg-purple-50" : "border-slate-200 bg-white",
      )}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          id={`tc-${entry.artifact_id}`}
          checked={checked}
          onChange={() => onToggle(entry.artifact_id)}
          className="mt-0.5 h-4 w-4 accent-purple-600 cursor-pointer shrink-0"
          aria-label={entry.title}
        />
        <label
          htmlFor={`tc-${entry.artifact_id}`}
          className="flex-1 cursor-pointer min-w-0"
        >
          <div className="flex items-center flex-wrap gap-1">
            <span className="text-sm font-medium text-slate-800">{entry.title}</span>
            {entry.from_current_thread && (
              <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-300">
                This conversation
              </Badge>
            )}
            <ConfidenceBadge level={entry.confidence_level} />
          </div>
          {entry.source_requirement_name && (
            <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
              <span>From:</span>
              {hasSource ? (
                <a
                  href={entry.source_url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="flex items-center gap-0.5 text-blue-600 hover:underline"
                >
                  {entry.source_requirement_name}
                  <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                <span>{entry.source_requirement_name}</span>
              )}
            </div>
          )}
        </label>
        {hasPreview && (
          <button
            type="button"
            onClick={() => setPreviewOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 shrink-0"
            aria-label={previewOpen ? "Hide preview" : "Show preview"}
          >
            {previewOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        )}
      </div>
      {previewOpen && entry.preview && (
        <div className="ml-7 text-xs text-slate-600 border-t pt-2 mt-1 leading-relaxed">
          {entry.preview}
        </div>
      )}
    </div>
  );
}

export function SarahInputSelection({
  testCases,
  onConfirm,
  onSkip,
  disabled = false,
}: SarahInputSelectionProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(testCases.filter((tc) => tc.default_selected).map((tc) => tc.artifact_id)),
  );

  function toggleEntry(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function handleSelectAll() {
    setSelected(new Set(testCases.map((tc) => tc.artifact_id)));
  }

  function handleSelectNone() {
    setSelected(new Set());
  }

  const currentThreadCount = testCases.filter((tc) => tc.from_current_thread).length;
  const selectedCount = selected.size;

  return (
    <div className="flex flex-col border rounded-md overflow-hidden bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Select test cases for script generation
          {currentThreadCount > 0 && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              ({currentThreadCount} from this conversation)
            </span>
          )}
        </div>
        <div className="flex gap-2 text-xs text-slate-500">
          <button
            type="button"
            onClick={handleSelectAll}
            disabled={disabled}
            className="hover:text-slate-700 disabled:opacity-50"
          >
            All
          </button>
          <span>/</span>
          <button
            type="button"
            onClick={handleSelectNone}
            disabled={disabled}
            className="hover:text-slate-700 disabled:opacity-50"
          >
            None
          </button>
        </div>
      </div>

      {/* Test case list */}
      <div className="flex flex-col gap-2 p-4 max-h-[60vh] overflow-y-auto">
        {testCases.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-4 bg-slate-50 border rounded-md">
            No test cases available. Please ask Mary to generate test cases first before running Sarah.
          </p>
        ) : (
          testCases.map((entry) => (
            <TestCaseRow
              key={entry.artifact_id}
              entry={entry}
              checked={selected.has(entry.artifact_id)}
              onToggle={toggleEntry}
            />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t px-4 py-3 bg-slate-50">
        <span className="text-xs text-slate-500">
          {selectedCount} of {testCases.length} selected
        </span>
        <button
          type="button"
          onClick={
            selectedCount === 0 ? () => onSkip?.() : () => onConfirm(Array.from(selected))
          }
          disabled={disabled}
          className="bg-purple-600 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {selectedCount === 0 ? "Skip →" : "Confirm & Generate →"}
        </button>
      </div>
    </div>
  );
}
