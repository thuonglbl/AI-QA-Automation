import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { listSessions } from "@/lib/sessions";
import type { SessionMatrix } from "@/types/session";
import { TestCredentialsEditor } from "./TestCredentialsEditor";

interface SessionMatrixPanelProps {
  projectId: string;
  projectName?: string | null;
  open: boolean;
  onClose: () => void;
}


/**
 * Per-user test-account session viewer (project-scoped), rendered as an
 * (environment × role) matrix. Each cell shows whether there is a valid generated session
 * for that slot. Sarah (debug) and Jack (run) rehydrate the session server-side.
 */
export function SessionMatrixPanel({
  projectId,
  projectName,
  open,
  onClose,
}: SessionMatrixPanelProps) {
  const [matrix, setMatrix] = useState<SessionMatrix | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setMatrix(await listSessions(projectId));
    } catch {
      setLoadError("Could not load sessions for this project.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open && projectId) {
      void refresh();
    }
  }, [open, projectId, refresh]);

  if (!open) return null;

  const environments = matrix?.environments ?? [];
  const roles = matrix?.app_roles ?? [];


  const ready = matrix && !loading;
  const hasMatrix = environments.length > 0 && roles.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Test accounts"
      onClick={onClose}
    >
      <div
        className="mt-10 flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Test Accounts</h2>
            {projectName && <span className="text-xs text-slate-500">{projectName}</span>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
          <div className="mb-2">
            <p className="text-sm text-slate-500">
              Configure test account credentials for auto-login. Credentials are encrypted and stored in your personal secure vault.
            </p>
          </div>

          {loading && <p className="text-sm text-slate-500">Loading sessions…</p>}
          {loadError && <p className="text-sm text-red-600">{loadError}</p>}

          {ready && !hasMatrix && (
            <p className="text-sm text-slate-500">
              This project has no environments and roles configured yet. Ask a project admin to
              add them in the Project Admin dashboard.
            </p>
          )}

          {ready && hasMatrix && (
            <div className="overflow-x-auto rounded-md border">
              <div className="p-4">
                <TestCredentialsEditor
                  projectId={projectId}
                  environments={environments}
                  roles={roles}
                />
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
