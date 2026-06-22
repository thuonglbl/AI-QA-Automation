import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { ExecutionRunSummary } from "@/types/execution";

interface ExecutionHistoryProps {
  projectId: string;
  /** When set, scope the history to a single thread (AC3 thread filter). */
  threadId?: string;
  onOpenRun?: (run: ExecutionRunSummary) => void;
}

const RESULT_OPTIONS = ["", "passed", "failed", "error"];

/** Story 14.6 AC3: run-time-sorted, filterable execution history (thread/browser/result/date). */
export function ExecutionHistory({ projectId, threadId, onOpenRun }: ExecutionHistoryProps) {
  const [runs, setRuns] = useState<ExecutionRunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [browser, setBrowser] = useState("");
  const [result, setResult] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (threadId) params.set("thread_id", threadId);
    if (browser) params.set("browser", browser);
    if (result) params.set("result", result);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const qs = params.toString();
    apiFetch<ExecutionRunSummary[]>(
      `/projects/${projectId}/executions${qs ? `?${qs}` : ""}`,
    )
      .then((data) => setRuns(data))
      .catch(() => setError("Could not load execution history."))
      .finally(() => setLoading(false));
  }, [projectId, threadId, browser, result, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-3 border border-slate-200 rounded-md bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">Execution history</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 text-xs">
        <input
          aria-label="Browser filter"
          placeholder="Browser"
          value={browser}
          onChange={(e) => setBrowser(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1"
        />
        <select
          aria-label="Result filter"
          value={result}
          onChange={(e) => setResult(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1"
        >
          {RESULT_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r === "" ? "Any result" : r}
            </option>
          ))}
        </select>
        <input
          aria-label="From date"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1"
        />
        <input
          aria-label="To date"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1"
        />
      </div>

      {loading && <p className="text-xs text-slate-500">Loading…</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {!loading && !error && runs.length === 0 && (
        <p className="text-xs text-slate-500">No execution runs yet.</p>
      )}

      <div className="flex flex-col gap-1">
        {runs.map((run) => (
          <button
            key={run.run_id}
            type="button"
            onClick={() => onOpenRun?.(run)}
            className="flex items-center justify-between text-left text-xs border border-slate-200 rounded px-3 py-2 hover:bg-slate-50"
          >
            <span className="text-slate-600">
              {new Date(run.created_at).toLocaleString()} · {run.browsers.join(", ") || "—"}
            </span>
            <span className="flex gap-2">
              <span className="text-green-700">{run.passed}✓</span>
              <span className="text-red-700">{run.failed}✗</span>
              <span className="text-amber-700">{run.errors}!</span>
              <span className="text-slate-500">{run.success_rate}%</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
