import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ScriptInput } from "@/types/script";

export interface ProjectEnvironment {
  name: string;
  url: string;
}

export interface CapturedSessionSlot {
  environment: string;
  role: string;
  /** ISO expiry of the captured session; past this it can't be used (auto-login ignores it). */
  expires_at?: string | null;
}

/** Confirm payload Jack's panel emits (full-stack sync with the backend confirm data). */
export interface JackRunConfig {
  targetUrl: string;
  environment: string;
  role: string;
  browsers: string[];
}

interface JackInputSelectionProps {
  scripts: ScriptInput[];
  environments?: ProjectEnvironment[];
  appRoles?: string[];
  sessions?: CapturedSessionSlot[];
  onConfirm: (selectedIds: string[], config: JackRunConfig) => void;
  /**
   * Opens the test-account session flow (the Sessions matrix panel).
   */
  onCaptureSession?: () => void;
  disabled?: boolean;
  /** True while a confirmed run is starting/in flight — disables the button and shows a spinner
   *  so the user gets feedback and cannot launch duplicate runs by clicking again. */
  running?: boolean;
}

// Chrome and Edge are Chromium channels (same engine), so the headless Chromium build covers
// both — we offer one "Chromium" option instead of three. Only engines installed in the
// backend image are listed (see Dockerfile.backend: chromium, firefox, webkit).
const BROWSER_CHOICES: { label: string; name: string }[] = [
  { label: "chromium", name: "Chromium (Chrome, Edge)" },
  { label: "firefox", name: "Firefox" },
  { label: "webkit", name: "WebKit" },
];

function ScriptRow({
  entry,
  checked,
  onToggle,
}: {
  entry: ScriptInput;
  checked: boolean;
  onToggle: (id: string) => void;
}) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const hasPreview = !!entry.preview;
  const hasConfidence = entry.confidence !== null && entry.confidence !== undefined;

  return (
    <div
      className={cn(
        "border rounded-md px-4 py-3 flex flex-col gap-2 transition-colors",
        checked ? "border-orange-300 bg-orange-50" : "border-slate-200 bg-white",
      )}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          id={`script-${entry.artifact_id}`}
          checked={checked}
          onChange={() => onToggle(entry.artifact_id)}
          className="mt-0.5 h-4 w-4 accent-orange-600 cursor-pointer shrink-0"
          aria-label={entry.title}
        />
        <label htmlFor={`script-${entry.artifact_id}`} className="flex-1 cursor-pointer min-w-0">
          <div className="flex items-center flex-wrap gap-1">
            <span className="text-sm font-medium text-slate-800">{entry.title}</span>
            {entry.from_current_thread && (
              <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-300">
                This conversation
              </Badge>
            )}
            {entry.role && (
              <Badge
                variant="outline"
                className="text-xs bg-orange-50 text-orange-700 border-orange-300"
              >
                {entry.role}
              </Badge>
            )}
            {hasConfidence && (
              <Badge
                variant="outline"
                className="text-xs bg-slate-100 text-slate-600 border-slate-300"
              >
                {Math.round((entry.confidence ?? 0) * 100)}%
              </Badge>
            )}
          </div>
          {entry.source_test_case_title && (
            <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
              <span>From test case:</span>
              <span>{entry.source_test_case_title}</span>
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
        <pre className="ml-7 text-xs text-slate-600 border-t pt-2 mt-1 leading-relaxed overflow-x-auto whitespace-pre-wrap">
          {entry.preview}
        </pre>
      )}
    </div>
  );
}

export function JackInputSelection({
  scripts,
  environments = [],
  appRoles = [],
  onConfirm,
  disabled = false,
  running = false,
}: JackInputSelectionProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(scripts.filter((s) => s.default_selected).map((s) => s.artifact_id)),
  );
  // Local guard so a rapid second click can't fire onConfirm before the parent's `running`
  // state propagates. Clears when the parent says the run is no longer starting (e.g. it
  // errored back to the selection panel) or a fresh selection panel arrives.
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    if (!running) setSubmitting(false);
  }, [running, scripts]);
  const isRunning = submitting || running;
  const hasEnvironments = environments.length > 0;
  const [environmentName, setEnvironmentName] = useState<string>(
    () => environments[0]?.name ?? "",
  );
  const [freeUrl, setFreeUrl] = useState<string>("");
  const [role, setRole] = useState<string>(() => appRoles[0] ?? "");
  const [browsers, setBrowsers] = useState<Set<string>>(() => new Set(["chromium"]));

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

  function toggleBrowser(label: string) {
    setBrowsers((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  }

  const currentThreadCount = scripts.filter((s) => s.from_current_thread).length;
  const selectedCount = selected.size;
  const selectedEnv = environments.find((e) => e.name === environmentName);
  const targetUrl = hasEnvironments ? (selectedEnv?.url ?? "") : freeUrl.trim();

  // Backend will auto-login via TestAccountCredential if session is missing.
  // We no longer block the frontend run if the session is not yet cached.
  const allRolesHaveSession = true;
  const canRun =
    selectedCount > 0 && browsers.size > 0 && targetUrl.length > 0 && allRolesHaveSession;

  let disabledReason = "";
  if (!canRun) {
    if (selectedCount === 0) disabledReason = "Select at least one script to run";
    else if (targetUrl.length === 0) disabledReason = "Configure target environment first";
    else if (browsers.size === 0) disabledReason = "Select at least one browser";
    else if (!allRolesHaveSession) disabledReason = "All roles must have a captured session";
  }

  function handleConfirm() {
    if (isRunning) return; // prevent duplicate runs from a double-click
    setSubmitting(true);
    onConfirm(Array.from(selected), {
      targetUrl,
      environment: environmentName,
      role,
      browsers: Array.from(browsers),
    });
  }

  return (
    <div className="flex flex-col border rounded-md overflow-hidden bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Select scripts to run
          {currentThreadCount > 0 && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              ({currentThreadCount} from this conversation)
            </span>
          )}
        </div>
        <div className="flex gap-2 text-xs text-slate-500">
          <button
            type="button"
            onClick={() => setSelected(new Set(scripts.map((s) => s.artifact_id)))}
            disabled={disabled}
            className="hover:text-slate-700 disabled:opacity-50"
          >
            All
          </button>
          <span>/</span>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            disabled={disabled}
            className="hover:text-slate-700 disabled:opacity-50"
          >
            None
          </button>
        </div>
      </div>

      {/* Script list */}
      <div className="flex flex-col gap-2 p-4 max-h-[40vh] overflow-y-auto">
        {scripts.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-4">No scripts available.</p>
        ) : (
          scripts.map((entry) => (
            <ScriptRow
              key={entry.artifact_id}
              entry={entry}
              checked={selected.has(entry.artifact_id)}
              onToggle={toggleEntry}
            />
          ))
        )}
      </div>

      {/* Environment + role + browsers */}
      <div className="flex flex-col gap-3 border-t px-4 py-3 bg-slate-50">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="jack-target-url" className="text-xs font-medium text-slate-600">
              Target environment
            </label>
            {hasEnvironments ? (
              <select
                id="jack-target-url"
                aria-label="Target environment"
                value={environmentName}
                onChange={(e) => setEnvironmentName(e.target.value)}
                disabled={disabled}
                className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              >
                {environments.map((env) => (
                  <option key={env.name} value={env.name}>
                    {env.name} — {env.url}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="jack-target-url"
                type="url"
                aria-label="Application URL"
                value={freeUrl}
                onChange={(e) => setFreeUrl(e.target.value)}
                disabled={disabled}
                placeholder="https://app.example.com"
                className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              />
            )}
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="jack-role" className="text-xs font-medium text-slate-600">
              Default login role
            </label>
            <select
              id="jack-role"
              aria-label="Login role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={disabled || appRoles.length === 0}
              className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
            >
              {appRoles.length === 0 ? (
                <option value="">No roles configured</option>
              ) : (
                appRoles.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Browsers</span>
          <div className="flex flex-wrap gap-3">
            {BROWSER_CHOICES.map((b) => (
              <label key={b.label} className="flex items-center gap-1 text-xs text-slate-700">
                <input
                  type="checkbox"
                  aria-label={b.name}
                  checked={browsers.has(b.label)}
                  onChange={() => toggleBrowser(b.label)}
                  disabled={disabled}
                  className="h-4 w-4 accent-orange-600"
                />
                {b.name}
              </label>
            ))}
          </div>
        </div>

        <div className="mt-2 flex items-start gap-2 bg-amber-50 text-amber-800 p-3 rounded-md border border-amber-200">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <p className="text-xs leading-relaxed">
            <strong>Note for Scheduled Tests:</strong> If the environment uses Interactive MFA (waiting for an Authenticator code), overnight or scheduled runs will timeout when they hit the MFA screen. To fully automate scheduled tests, please configure a <strong>TOTP Secret</strong> in the Project Test Accounts settings instead.
          </p>
        </div>

        {!hasEnvironments && selectedCount > 0 && (
          <p className="text-xs text-amber-700">
            This project has no configured environments. A run needs an environment to resolve
            the corresponding Test Account, so a project admin must add an environment before Jack
            can run.
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t px-4 py-3 bg-slate-50">
        <span className="text-xs text-slate-500">
          {selectedCount} of {scripts.length} selected
        </span>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-block">
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={disabled || !canRun || isRunning}
                  className="inline-flex items-center bg-orange-600 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Running…
                    </>
                  ) : (
                    "Confirm & Run →"
                  )}
                </button>
              </span>
            </TooltipTrigger>
            {(disabled || !canRun) && !isRunning && (
              <TooltipContent side="top">
                <p>{disabled ? "Run is disabled" : disabledReason}</p>
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );
}
