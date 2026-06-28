import { useState, useEffect } from "react";
import { ExternalLink, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface BobRequirementReviewProps {
  data: {
    page_title: string;
    markdown: string;
    source_url: string;
  };
  totalPages: number;
  currentIndex: number;
  onApprove: (updatedMarkdown: string) => void;
  disabled?: boolean;
}

export function BobRequirementReview({
  data,
  totalPages,
  currentIndex,
  onApprove,
  disabled,
}: BobRequirementReviewProps) {
  const [markdown, setMarkdown] = useState(data.markdown);

  // Sync state if data changes
  useEffect(() => {
    setMarkdown(data.markdown);
  }, [data.markdown]);

  return (
    <div className="w-[85%] max-w-4xl self-start">
      <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Bob</div>
      <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col">
        <div className="px-5 py-3.5 border-b border-[#e2e8f0] bg-[#f8fafc] flex justify-between items-center">
          <div>
            <h4 className="font-semibold text-[14px]">
              Review Requirement Page ({currentIndex + 1} of {totalPages})
            </h4>
            <div className="text-xs text-[#64748b] mt-0.5">
              {data.page_title}
            </div>
          </div>
          {data.source_url && (
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#3b82f6] hover:text-[#2563eb] text-xs font-medium flex items-center gap-1.5 transition-colors bg-blue-50 px-3 py-1.5 rounded-full hover:bg-blue-100"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              View in Confluence
            </a>
          )}
        </div>

        <div className="p-0 border-b border-[#e2e8f0]">
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            disabled={disabled}
            className="w-full h-[400px] p-5 text-sm font-mono focus:outline-none resize-y bg-white"
            placeholder="Review and edit the markdown content here..."
          />
        </div>

        <div className="px-5 py-3.5 bg-[#f8fafc] flex justify-center">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    onClick={() => onApprove(markdown)}
                    disabled={disabled}
                    className="bg-[#3b82f6] hover:bg-[#2563eb] text-white flex items-center gap-2 min-w-[120px] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Check className="w-4 h-4" />
                    OK
                  </Button>
                </span>
              </TooltipTrigger>
              {disabled && (
                <TooltipContent side="top">
                  <p>Review unavailable: please answer the active prompt first</p>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  );
}
