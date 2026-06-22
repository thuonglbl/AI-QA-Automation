import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ExecutionResultDetail } from "@/components/agents/ExecutionResultDetail";
import type { ExecutionDetail, ExecutionSummary } from "@/types/execution";

interface JackExecutionReportProps {
  projectId: string;
  summary: ExecutionSummary;
}

function statusChipClass(status: string): string {
  if (status === "passed") return "bg-green-50 text-green-700 border-green-300";
  if (status === "failed") return "bg-red-50 text-red-700 border-red-300";
  if (status === "error") return "bg-amber-50 text-amber-700 border-amber-300";
  return "bg-slate-50 text-slate-500 border-slate-300";
}

/** Attachment-map key. MUST stay byte-identical with the backend `attachment_key`
 * (execution_report.py) and the key Jack builds (jack.py) — role-aware so the same
 * (test, browser) under different roles does not collide. */
function attachmentKey(testName: string, browser: string, role?: string | null): string {
  return role ? `${role}::${testName}::${browser}` : `${testName}::${browser}`;
}

/** Story 14.6 AC1+AC2: the run report — summary card + per-test results table with
 * row-select → drilldown. Fetches the full run detail from the executions API. */
export function JackExecutionReport({ projectId, summary }: JackExecutionReportProps) {
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const runId = summary.run_id;
    if (!runId) return;
    setDetail(null);
    setSelected(null);
    setError(null);
    apiFetch<ExecutionDetail>(`/projects/${projectId}/executions/${runId}`)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load execution detail.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, summary.run_id]);

  const total = summary.total || 1;
  const passPct = Math.round((summary.passed / total) * 100);
  const results = detail?.results ?? [];
  const anyRole = results.some((r) => r.role);

  return (
    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
      {/* Summary */}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-slate-700">
          Execution report
          {summary.browsers.length > 0 && ` (${summary.browsers.join(", ")})`}
        </p>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="px-2 py-0.5 rounded-full border bg-slate-50 text-slate-700">
            {summary.total} total
          </span>
          <span className="px-2 py-0.5 rounded-full border border-green-300 bg-green-50 text-green-700">
            {summary.passed} passed
          </span>
          <span className="px-2 py-0.5 rounded-full border border-red-300 bg-red-50 text-red-700">
            {summary.failed} failed
          </span>
          <span className="px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700">
            {summary.errors} errors
          </span>
          {summary.skipped > 0 && (
            <span className="px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500">
              {summary.skipped} skipped
            </span>
          )}
          <span className="px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500">
            {(summary.duration_ms / 1000).toFixed(1)}s
          </span>
        </div>
        {/* Success-rate bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-green-500" style={{ width: `${passPct}%` }} />
          </div>
          <span className="text-xs text-slate-500">{passPct}% pass</span>
        </div>
        {summary.unavailable_browsers.length > 0 && (
          <p className="text-xs text-amber-700">
            Unavailable:{" "}
            {summary.unavailable_browsers.map((b) => `${b.label} (${b.reason})`).join(", ")}
          </p>
        )}
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* Per-test results table */}
      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-1 pr-2">Test</th>
                <th className="py-1 pr-2">Browser</th>
                {anyRole && <th className="py-1 pr-2">Role</th>}
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2">Duration</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr
                  key={`${r.test_name}-${r.browser}-${i}`}
                  onClick={() => setSelected(selected === i ? null : i)}
                  className={cn(
                    "border-b cursor-pointer hover:bg-slate-50",
                    selected === i && "bg-orange-50",
                  )}
                >
                  <td className="py-1 pr-2">{r.test_name}</td>
                  <td className="py-1 pr-2">{r.browser}</td>
                  {anyRole && <td className="py-1 pr-2 text-slate-600">{r.role || "-"}</td>}
                  <td className="py-1 pr-2">
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded-full border text-[11px]",
                        statusChipClass(r.status),
                      )}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="py-1 pr-2 text-slate-500">
                    {r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(2)}s` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Drilldown */}
      {selected != null && results[selected] && (
        <ExecutionResultDetail
          projectId={projectId}
          result={results[selected]!}
          attachment={
            detail?.attachments?.[
              attachmentKey(
                results[selected]!.test_name,
                results[selected]!.browser,
                results[selected]!.role,
              )
            ]
          }
        />
      )}
    </div>
  );
}
