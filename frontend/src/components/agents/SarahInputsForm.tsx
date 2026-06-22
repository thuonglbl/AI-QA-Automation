import { useState } from "react";

export interface SarahInputsRequest {
  needsUrl: boolean;
  needsChrome: boolean;
  chromeOnFile: boolean;
  chromeExample: string;
  cdpExample: string;
  /** Project-wide target environments (name + URL) the admin configured. When present,
   *  Sarah asks the user to PICK one instead of typing a URL. */
  environments: { name: string; url: string }[];
}

interface SarahInputsFormProps {
  request: SarahInputsRequest;
  onSubmit: (targetUrl: string, chromePath: string, cdpUrl: string) => void;
  disabled?: boolean;
}

/**
 * Collects the inputs Sarah needs to drive the real app with browser-use:
 * the application URL (always asked), and how to reach the browser — either a
 * Chrome debug URL to REUSE a logged-in (SSO) session, or a Chrome executable to
 * launch a fresh browser. Submitting re-starts Sarah's step so the live
 * exploration can run.
 */
export function SarahInputsForm({ request, onSubmit, disabled = false }: SarahInputsFormProps) {
  const [targetUrl, setTargetUrl] = useState("");
  const [selectedEnvUrl, setSelectedEnvUrl] = useState("");
  const [chromePath, setChromePath] = useState("");
  const [cdpUrl, setCdpUrl] = useState("");

  // When the project defines environments, the user PICKS one (its URL is the target);
  // otherwise we fall back to a free-text URL so Sarah is never a dead end.
  const hasEnvironments = request.environments.length > 0;
  const effectiveUrl = hasEnvironments ? selectedEnvUrl : targetUrl.trim();

  const urlOk = !request.needsUrl || effectiveUrl.startsWith("http");
  // A browser source is satisfied by a CDP URL (reuse session) OR a Chrome path
  // (launch). When Chrome is already on file, neither is required.
  const hasBrowserSource =
    !request.needsChrome || chromePath.trim().length > 0 || cdpUrl.trim().length > 0;
  const canSubmit = !disabled && urlOk && hasBrowserSource;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(effectiveUrl, chromePath.trim(), cdpUrl.trim());
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg border border-[#e2e8f0] text-sm outline-none " +
    "focus:border-[#8B5CF6] focus:ring-2 focus:ring-[#8B5CF6]/10";

  return (
    <div
      data-testid="sarah-inputs-form"
      className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm p-5 flex flex-col gap-4"
    >
      <p className="text-sm text-[#334155]">
        Sarah will drive Chrome through your approved test cases against the real
        application to capture real selectors, then generate Playwright scripts.
      </p>

      {request.needsUrl &&
        (hasEnvironments ? (
          <div className="flex flex-col gap-1">
            <label htmlFor="sarah-environment" className="text-xs font-medium text-[#475569]">
              Target environment
            </label>
            <select
              id="sarah-environment"
              data-testid="sarah-environment"
              value={selectedEnvUrl}
              onChange={(e) => setSelectedEnvUrl(e.target.value)}
              disabled={disabled}
              className={inputClass}
            >
              <option value="">Select environment…</option>
              {request.environments.map((env) => (
                <option key={env.name} value={env.url}>
                  {env.name} — {env.url}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-[#94a3b8]">
              Environments are configured per project in the Admin Dashboard.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <label htmlFor="sarah-target-url" className="text-xs font-medium text-[#475569]">
              Application URL
            </label>
            <input
              id="sarah-target-url"
              type="url"
              data-testid="sarah-target-url"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://your-app.example/page"
              disabled={disabled}
              className={inputClass}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
            />
            <p className="text-[11px] text-[#94a3b8]">
              Tip: configure reusable environments per project in the Admin Dashboard.
            </p>
          </div>
        ))}

      {/* SSO reuse (recommended): connect to a running Chrome instead of launching. */}
      <div className="flex flex-col gap-1">
        <label htmlFor="sarah-cdp-url" className="text-xs font-medium text-[#475569]">
          Reuse logged-in Chrome (SSO) — debug URL{" "}
          <span className="font-normal text-[#94a3b8]">(optional)</span>
        </label>
        <input
          id="sarah-cdp-url"
          type="url"
          data-testid="sarah-cdp-url"
          value={cdpUrl}
          onChange={(e) => setCdpUrl(e.target.value)}
          placeholder={request.cdpExample || "http://localhost:9222"}
          disabled={disabled}
          className={inputClass}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />
        <p className="text-[11px] text-[#94a3b8]">
          To reuse your authenticated session, start Chrome with{" "}
          <code>--remote-debugging-port=9222</code> (logged into the app), then enter{" "}
          <code>http://localhost:9222</code>. Leave blank to launch a fresh browser.
        </p>
      </div>

      {request.needsChrome ? (
        <div className="flex flex-col gap-1">
          <label htmlFor="sarah-chrome-path" className="text-xs font-medium text-[#475569]">
            Chrome executable path{" "}
            <span className="font-normal text-[#94a3b8]">(if not reusing a session above)</span>
          </label>
          <input
            id="sarah-chrome-path"
            type="text"
            data-testid="sarah-chrome-path"
            value={chromePath}
            onChange={(e) => setChromePath(e.target.value)}
            placeholder={request.chromeExample}
            disabled={disabled}
            className={inputClass}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </div>
      ) : (
        request.chromeOnFile && (
          <p className="text-xs text-[#64748b]" data-testid="sarah-chrome-on-file">
            Using your saved Chrome path (or the debug URL above, if provided).
          </p>
        )
      )}

      <button
        onClick={submit}
        disabled={!canSubmit}
        data-testid="sarah-inputs-submit"
        className="self-start bg-[#8B5CF6] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#7c3aed] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Generate scripts
      </button>
    </div>
  );
}
