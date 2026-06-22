/** Confidence level band for a generated test case (matches backend Literal). */
export type ConfidenceLevel = "high" | "medium" | "low";

/** A single step in a test case. */
export interface TestCaseStep {
  number: number;
  action: string;
  target: string;
  data?: string;
}

/** A generated test case — full-stack sync with backend TestCase.model_dump(). */
export interface TestCase {
  title: string;
  objective?: string;
  preconditions: string[];
  test_data?: string[];
  steps: TestCaseStep[];
  expected_results: string[];
  automation_hints?: string[];
  tags?: string[];
  source_requirement_id?: string | null;
  source_requirement_name?: string | null;
  source_url?: string | null;
  feature_area?: string | null;
  role?: string | null;
  warnings?: string[];
  confidence?: number | null;
  confidence_level?: ConfidenceLevel | null;
  confidence_rationale?: string[];
  approved_by?: string | null;
  approved_at?: string | null;
}

/**
 * One entry in Mary's QA review panel. The test case itself is the rendered
 * **Markdown** document (`markdown`) — the same body that is stored and fed to the
 * LLM; no structured-JSON test case is sent. The remaining fields are review-only
 * metadata (confidence band/score/rationale, the warnings behind it, approval state)
 * that lives outside the test case document.
 */
export interface MaryReviewCase {
  title: string;
  markdown: string;
  confidence?: number | null;
  confidence_level?: ConfidenceLevel | null;
  confidence_rationale?: string[];
  warnings?: string[];
  approved_at?: string | null;
}

/** Review payload emitted by Mary after generation (metadata.type === "test_case_review"). */
export interface TestCaseReviewPayload {
  type: "test_case_review";
  test_cases: MaryReviewCase[];
  low_confidence_count?: number;
}

/** Review status for an individual generated script (client-side derived). */
export type ScriptReviewStatus = "approved" | "skipped" | "pending";

/** One entry in the present-all script_review payload. */
export interface ScriptReviewItem {
  index: number;
  test_case: TestCase;
  script_content: string;
  script_language: string;
  file_path: string;
  confidence: number;
  warnings?: string[];
  approved: boolean;
  /** AC1 (13.7): who approved this script (user email or user id). */
  approved_by?: string | null;
  /** AC1 (13.7): ISO-8601 timestamp of approval. */
  approved_at?: string | null;
  status: ScriptReviewStatus;
  error_message?: string | null;
}

/** Present-all payload emitted by Sarah after generation (metadata.type === "script_review"). */
export interface ScriptReviewPayload {
  type: "script_review";
  scripts: ScriptReviewItem[];
  current_index: number;
  total_count: number;
}

/** A single validation finding from the backend (metadata.type === "script_validation_error"). */
export interface ScriptValidationError {
  line?: number | null;
  column?: number | null;
  message: string;
  severity: "error" | "warning";
  code: "syntax" | "unsafe_pattern";
}

/** Payload emitted by Sarah on a failed edited-approve (metadata.type === "script_validation_error"). */
export interface ScriptValidationPayload {
  type: "script_validation_error";
  script_index: number;
  errors: ScriptValidationError[];
}

/** One candidate entry in Sarah's input-selection panel (metadata.type === "test_case_selection"). */
export interface TestCaseInput {
  artifact_id: string;
  name: string;
  title: string;
  source_requirement_name?: string | null;
  source_url?: string | null;
  confidence_level?: ConfidenceLevel | null;
  from_current_thread: boolean;
  default_selected: boolean;
  preview?: string | null;
}
