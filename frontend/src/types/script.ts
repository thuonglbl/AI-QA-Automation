/**
 * One candidate entry in Jack's input-selection panel
 * (metadata.type === "script_selection").
 *
 * Full-stack sync with the backend `script_selection` payload emitted by
 * `JackAgent._present_script_selection` (Story 14.1).
 */
export interface ScriptInput {
  artifact_id: string;
  name: string;
  title: string;
  from_current_thread: boolean;
  default_selected: boolean;
  preview?: string | null;
  source_test_case_title?: string | null;
  confidence?: number | null;
  /** App role the script runs AS (Slice 6). Drives per-role session validation + grouping. */
  role?: string | null;
}
