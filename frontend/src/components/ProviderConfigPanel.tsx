import type { ProviderConfigResponse } from "@/types/provider";

interface ProviderConfigPanelProps {
  config: ProviderConfigResponse;
  onChangeConfig: () => void;
  onClose: () => void;
}

export function ProviderConfigPanel({
  config,
  onChangeConfig,
  onClose,
}: ProviderConfigPanelProps) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-label="Provider configuration"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[#0f172a]">
            Provider Configuration
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-[#64748b] hover:text-[#0f172a] text-xl leading-none"
          >
            ×
          </button>
        </div>

        {!config.configured ? (
          <p className="text-sm text-[#64748b]">No provider configured yet.</p>
        ) : (
          <>
            <div className="mb-4 space-y-1">
              <div className="text-xs text-[#64748b] uppercase tracking-wide font-medium">
                Provider
              </div>
              <div className="text-sm font-medium text-[#0f172a]">
                {config.provider_name ?? config.provider}
              </div>
              {config.endpoint && (
                <div className="text-xs text-[#94a3b8] font-mono break-all">
                  {config.endpoint}
                </div>
              )}
              {config.source && (
                <div className="text-xs text-[#64748b]">
                  Source:{" "}
                  <span className="font-medium">
                    {config.source === "thread"
                      ? "this thread"
                      : config.source === "saved"
                        ? "saved (project default)"
                        : "none"}
                  </span>
                </div>
              )}
            </div>

            {config.agents.length > 0 && (
              <div className="mb-4">
                <div className="text-xs text-[#64748b] uppercase tracking-wide font-medium mb-2">
                  Agent Models
                </div>
                <div className="space-y-2">
                  {config.agents.map((a) => (
                    <div
                      key={a.agent}
                      className="bg-[#f8fafc] border border-[#e2e8f0] rounded-lg px-3 py-2"
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-xs font-semibold text-[#0f172a] capitalize">
                          {a.agent}
                        </span>
                        <span className="text-xs text-[#64748b] font-mono truncate">
                          {a.model ?? "—"}
                        </span>
                      </div>
                      {a.rationale && (
                        <p className="text-[11px] text-[#94a3b8] mt-0.5 leading-snug">
                          {a.rationale}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-[#f1f5f9]">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-full text-sm text-[#64748b] hover:bg-[#f1f5f9] transition-colors"
          >
            Close
          </button>
          <button
            onClick={onChangeConfig}
            data-testid="change-config-btn"
            className="px-4 py-2 rounded-full text-sm bg-[#3b82f6] text-white hover:bg-[#2563eb] transition-colors"
          >
            Change configuration
          </button>
        </div>
      </div>
    </div>
  );
}
