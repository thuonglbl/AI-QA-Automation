import React, { useState } from "react";
import { X, KeyRound, Loader2, AlertCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface InteractiveMFAPromptProps {
  projectId: string;
  sessionId: string;
  environment: string;
  role: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function InteractiveMFAPrompt({
  projectId,
  sessionId,
  environment,
  role,
  onClose,
  onSuccess,
}: InteractiveMFAPromptProps) {
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;

    setIsSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/projects/${projectId}/test-credentials/submit-mfa`, {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          code: code.trim(),
        }),
      });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit MFA code");
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        className="w-full max-w-sm rounded-xl bg-white p-6 shadow-2xl ring-1 ring-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
              <KeyRound className="h-4 w-4" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900">MFA Required</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="text-slate-400 hover:text-slate-600 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-slate-600 mb-5">
          The bot is waiting for your 6-digit Authenticator code to login as{" "}
          <span className="font-semibold">{role}</span> on{" "}
          <span className="font-semibold">{environment}</span>.
        </p>

        {error && (
          <div className="flex items-start gap-2 px-3 py-2.5 mb-4 rounded-lg bg-red-50 border border-red-200">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
            <span className="text-sm font-medium text-red-800">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="text"
              autoFocus
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="e.g. 123456"
              disabled={isSubmitting}
              className="w-full text-center tracking-widest text-2xl font-mono px-3 py-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow disabled:opacity-60"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-200 transition-colors disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || code.length < 6}
              className="inline-flex items-center justify-center min-w-[100px] px-4 py-2 text-sm font-medium text-white bg-indigo-600 border border-transparent rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors disabled:opacity-60"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Sending
                </>
              ) : (
                "Submit Code"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
