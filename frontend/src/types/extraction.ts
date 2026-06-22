/** Quality issue attached to an extracted page by the backend's deterministic scan (Story 11.5). */
export interface QualityIssue {
  category: string;
  location: string;
  message: string;
  impact: string;
}

/** A single extracted page returned in the `is_review_ready` payload. */
export interface ExtractedPage {
  page_id: string;
  page_title: string;
  source_url: string;
  raw_html: string;
  requirement_md: string;
  /** Raw parser warnings from Story 11.3 (unsupported content, gliffy, etc.) */
  warnings?: string[];
  /** Deterministic quality issues from Story 11.5 */
  quality_issues?: QualityIssue[];
  /** "confluence" | "jira" — set by Story 11.4 for Jira items */
  source_type?: string;
}
