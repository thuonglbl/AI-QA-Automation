import { useEffect, useState } from "react";
import { X, FileText } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { ReviewContent } from "@/components/ReviewContent";
import type { Artifact } from "@/components/conversations/ProjectSidebar";

interface ArtifactPreviewProps {
  artifact: Artifact;
  onClose: () => void;
}

interface ArtifactContent {
  artifact_id: string;
  version: number;
  content: string;
  content_encoding: "text" | "base64";
}

export function ArtifactPreview({ artifact, onClose }: ArtifactPreviewProps) {
  const [content, setContent] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setContent(null);

    apiFetch<ArtifactContent>(
      `/projects/${artifact.project_id}/artifacts/${artifact.id}/content`,
    )
      .then((data) => {
        if (cancelled) return;
        setContent(data.content);
        setVersion(data.version);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load artifact content");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [artifact.project_id, artifact.id]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-[#e2e8f0] flex items-center gap-3 bg-white flex-shrink-0">
        <div className="w-9 h-9 rounded-full flex items-center justify-center bg-[#f1f5f9] text-[#64748b] flex-shrink-0">
          <FileText className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-[15px] font-semibold text-[#0f172a] leading-tight truncate">
            {artifact.name}
          </h3>
          <div className="text-xs text-[#64748b] mt-0.5">
            {artifact.kind}
            {version !== null && ` · v${version}`}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-[#64748b] hover:bg-[#f1f5f9] rounded-md transition-colors"
          aria-label="Close preview"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {isLoading && (
          <div className="flex items-center justify-center py-12 text-[#94a3b8] text-sm">
            Loading artifact content…
          </div>
        )}
        {error && (
          <div className="bg-[#fee2e2] text-[#ef4444] px-4 py-3 rounded text-sm border border-[#f87171]/20">
            {error}
          </div>
        )}
        {content !== null && !isLoading && (
          <ReviewContent content={content} className="max-h-none" />
        )}
      </div>
    </div>
  );
}
