/**
 * Execution-result types (Epic 14). Full-stack sync with the executions API
 * (`src/ai_qa/api/executions.py`) and the Jack `execution_summary` message.
 */

/** A browser reported unavailable in the runner environment (Story 14.4). */
export interface UnavailableBrowser {
  label: string;
  reason: string;
}

/** Minimal run summary emitted after a Jack execution (Story 14.2/14.4). */
export interface ExecutionSummary {
  run_id?: string | null;
  total: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  duration_ms: number;
  browsers: string[];
  unavailable_browsers: UnavailableBrowser[];
  /** Story 14.5: the composed report artifact id. */
  report_artifact_id?: string | null;
}

/** One run summary from `GET /executions` (Story 14.6). */
export interface ExecutionRunSummary {
  run_id: string;
  thread_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  total: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  success_rate: number;
  browsers: string[];
  unavailable_browsers: UnavailableBrowser[];
  report_artifact_id?: string | null;
}

/** One per-`(test, browser)` result from `GET /executions/{run_id}` (Story 14.6). */
export interface ExecutionResult {
  test_name: string;
  browser: string;
  /** App role the test ran AS (Slice 6 role-grouped runs); null for role-less runs. */
  role?: string | null;
  status: string;
  duration_ms?: number | null;
  failure_classification?: string | null;
  error_message?: string | null;
  stack_trace?: string | null;
  source_script_artifact_id?: string | null;
  source_test_case_artifact_id?: string | null;
}

/** Attachment ids for one `(test, browser)` (from report.json). */
export interface AttachmentLink {
  screenshot_id?: string | null;
  trace_id?: string | null;
  log_id?: string | null;
}

/** Full detail of one run from `GET /executions/{run_id}`. */
export interface ExecutionDetail {
  summary: ExecutionRunSummary;
  results: ExecutionResult[];
  attachments: Record<string, AttachmentLink>;
}

/** History filter controls (Story 14.6 AC3). */
export interface ExecutionHistoryFilters {
  thread_id?: string;
  browser?: string;
  result?: string;
  date_from?: string;
  date_to?: string;
}
