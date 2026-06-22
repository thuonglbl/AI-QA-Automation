import { useEffect, useState } from "react";
import { API_BASE_PATH, apiFetch } from "@/lib/api";
import type { AttachmentLink, ExecutionResult } from "@/types/execution";

interface ExecutionResultDetailProps {
  projectId: string;
  result: ExecutionResult;
  attachment?: AttachmentLink;
}

interface ArtifactContent {
  artifact_id: string;
  version: number;
  content: string;
  content_encoding: "text" | "base64";
}

function contentUrl(projectId: string, artifactId: string): string {
  return `${API_BASE_PATH}/projects/${projectId}/artifacts/${artifactId}/content`;
}

function base64ToBlob(base64: string, mime: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/** Fetch an artifact's content payload. The `/content` endpoint returns a JSON envelope
 * ({content, content_encoding}), NOT raw bytes — so binary attachments (screenshots, trace
 * zips) must be decoded client-side rather than pointed at directly with <img>/<a>. */
function useArtifactContent(projectId: string, artifactId: string | undefined) {
  const [data, setData] = useState<ArtifactContent | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!artifactId) {
      setData(null);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setData(null);
    setFailed(false);
    apiFetch<ArtifactContent>(`/projects/${projectId}/artifacts/${artifactId}/content`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, artifactId]);

  return { data, failed };
}

const notAvailable = <span className="text-slate-400">(not available)</span>;
const loading = <span className="text-slate-400">(loading…)</span>;

/** Per-test drilldown: linked script + source test case, failure details, safe stack trace,
 * inline screenshot, trace download, log view. Binary attachments are fetched and decoded
 * client-side; a missing or failed attachment degrades to "(not available)" — never a broken
 * image or crash. */
export function ExecutionResultDetail({
  projectId,
  result,
  attachment,
}: ExecutionResultDetailProps) {
  const [logOpen, setLogOpen] = useState(false);
  const isFailure = result.status === "failed" || result.status === "error";
  const att = attachment ?? {};

  const screenshot = useArtifactContent(projectId, att.screenshot_id ?? undefined);
  const trace = useArtifactContent(projectId, att.trace_id ?? undefined);
  const log = useArtifactContent(projectId, logOpen ? (att.log_id ?? undefined) : undefined);

  // Build a downloadable object URL for the trace zip; revoke it on change/unmount.
  const [traceUrl, setTraceUrl] = useState<string | null>(null);
  useEffect(() => {
    if (trace.data && trace.data.content_encoding === "base64") {
      const url = URL.createObjectURL(base64ToBlob(trace.data.content, "application/zip"));
      setTraceUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    setTraceUrl(null);
    return undefined;
  }, [trace.data]);

  const logText =
    log.data == null
      ? null
      : log.data.content_encoding === "base64"
        ? atob(log.data.content)
        : log.data.content;

  return (
    <div className="border border-slate-200 rounded-md p-4 flex flex-col gap-2 bg-white text-sm">
      <div className="font-medium text-slate-800">
        {result.test_name} <span className="text-slate-400">[{result.browser}]</span>
        {result.role && <span className="text-slate-400"> · {result.role}</span>}
      </div>

      {/* Linked source artifacts (text artifacts — opened in a new tab) */}
      <div className="flex flex-col gap-1 text-xs text-slate-600">
        <span>
          Script:{" "}
          {result.source_script_artifact_id ? (
            <a
              href={contentUrl(projectId, result.source_script_artifact_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              open script
            </a>
          ) : (
            notAvailable
          )}
        </span>
        <span>
          Source test case:{" "}
          {result.source_test_case_artifact_id ? (
            <a
              href={contentUrl(projectId, result.source_test_case_artifact_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              open test case
            </a>
          ) : (
            notAvailable
          )}
        </span>
      </div>

      {isFailure && (
        <div className="flex flex-col gap-1">
          {result.failure_classification && (
            <span className="text-xs text-red-700">
              Classification: {result.failure_classification}
            </span>
          )}
          {result.error_message && (
            <p className="text-xs text-slate-700">{result.error_message}</p>
          )}
          {result.stack_trace && (
            <pre className="text-[11px] text-slate-600 bg-slate-50 border rounded p-2 overflow-x-auto whitespace-pre-wrap">
              {result.stack_trace}
            </pre>
          )}
        </div>
      )}

      {/* Attachments */}
      <div className="flex flex-col gap-2 text-xs">
        <div>
          <span className="font-medium text-slate-600">Screenshot: </span>
          {!att.screenshot_id || screenshot.failed
            ? notAvailable
            : screenshot.data?.content_encoding === "base64"
              ? (
                  <img
                    src={`data:image/png;base64,${screenshot.data.content}`}
                    alt={`${result.test_name} screenshot`}
                    className="mt-1 max-w-full border rounded"
                  />
                )
              : screenshot.data
                ? notAvailable
                : loading}
        </div>
        <div>
          <span className="font-medium text-slate-600">Trace: </span>
          {!att.trace_id || trace.failed ? (
            notAvailable
          ) : traceUrl ? (
            <a
              href={traceUrl}
              download={`${result.test_name}-trace.zip`}
              className="text-blue-600 hover:underline"
            >
              download trace
            </a>
          ) : (
            loading
          )}
        </div>
        <div>
          <span className="font-medium text-slate-600">Log: </span>
          {att.log_id ? (
            <button
              type="button"
              onClick={() => setLogOpen((v) => !v)}
              className="text-blue-600 hover:underline"
            >
              {logOpen ? "hide log" : "view log"}
            </button>
          ) : (
            notAvailable
          )}
          {logOpen &&
            att.log_id &&
            (log.failed ? (
              <p className="mt-1 text-slate-400">(not available)</p>
            ) : logText == null ? (
              <p className="mt-1 text-slate-400">(loading…)</p>
            ) : (
              <pre className="mt-1 w-full max-h-40 overflow-auto border rounded bg-white p-2 text-[11px] whitespace-pre-wrap text-slate-700">
                {logText}
              </pre>
            ))}
        </div>
      </div>
    </div>
  );
}
