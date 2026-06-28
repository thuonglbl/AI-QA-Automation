import type { ProcessingIndicatorProps } from "@/types/pipeline";

export function ProcessingIndicator({
  message,
  isActive = true,
  agentName = "System",
}: ProcessingIndicatorProps) {
  return (
    <div className="max-w-[600px] self-start">
      <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">{agentName}</div>
      <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed">
        <div className="flex items-center gap-1">
          <span
            className={`w-1.5 h-1.5 rounded-full bg-[#94a3b8] ${isActive ? "animate-bounce" : ""}`}
            style={{ animationDelay: "0s" }}
          />
          <span
            className={`w-1.5 h-1.5 rounded-full bg-[#94a3b8] ${isActive ? "animate-bounce" : ""}`}
            style={{ animationDelay: "0.2s" }}
          />
          <span
            className={`w-1.5 h-1.5 rounded-full bg-[#94a3b8] ${isActive ? "animate-bounce" : ""}`}
            style={{ animationDelay: "0.4s" }}
          />
        </div>
        <span className="text-sm text-[#64748b] ml-2">{message}</span>
      </div>
    </div>
  );
}
