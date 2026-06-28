import { User, Bot } from "lucide-react";
import type { AgentMessage, ErrorInfo } from "@/types/pipeline";
import { cn } from "@/lib/utils";
import { ReviewContent } from "./ReviewContent";
import { ProcessingIndicator } from "./ProcessingIndicator";
import { ErrorFeedback } from "./ErrorFeedback";
import { MessageTime } from "./MessageTime";

export interface ChatMessageProps {
  message: AgentMessage;
  /** Callback when retry is triggered for error messages */
  onRetry?: () => void;
  /** Optional error info for error-type messages */
  errorInfo?: ErrorInfo;
  /** Optional processing message for processing-type messages */
  processingMessage?: string;
}

export function ChatMessage({
  message,
  onRetry,
  errorInfo,
  processingMessage,
}: ChatMessageProps) {
  const isAgent = message.sender === "agent";
  const isSystem = message.sender === "system";
  const isProcessing =
    message.messageType === "processing" || processingMessage !== undefined;
  const isError = message.messageType === "error" || errorInfo !== undefined;

  // Determine styling based on sender type and message type
  const getBubbleStyle = () => {
    if (isError) {
      return "bg-red-50 text-red-900 border border-red-200 rounded-bl-none";
    }
    if (isSystem) {
      return "bg-slate-100 text-slate-700 border border-slate-300 rounded-bl-none rounded-br-none";
    }
    if (isAgent) {
      return "bg-white text-slate-900 border border-slate-200 rounded-bl-none";
    }
    return "bg-blue-500 text-white rounded-br-none";
  };

  const getAvatarStyle = () => {
    if (isSystem) {
      return "border-slate-300 bg-slate-200 text-slate-600";
    }
    if (isAgent) {
      return "border-slate-200 bg-slate-50 text-slate-500";
    }
    return "border-blue-400 bg-blue-600 text-blue-50";
  };

  const getNameStyle = () => {
    if (isSystem) return "text-slate-600";
    if (isAgent) return "text-slate-700";
    return "text-blue-100";
  };

  return (
    <div
      className={cn(
        "flex w-full mb-4",
        isAgent || isSystem ? "justify-start" : "justify-end",
      )}
      role="listitem"
    >
      <div
        className={cn(
          "flex max-w-[80%] p-4 rounded-lg items-start gap-4 shadow-sm",
          getBubbleStyle(),
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            "flex-shrink-0 flex items-center justify-center h-8 w-8 rounded-full border",
            getAvatarStyle(),
          )}
        >
          {isAgent ? (
            <Bot className="h-5 w-5" />
          ) : isSystem ? (
            <Bot className="h-5 w-5" />
          ) : (
            <User className="h-5 w-5" />
          )}
        </div>

        {/* Content */}
        <div className="flex flex-col gap-1 w-full min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("text-xs font-semibold", getNameStyle())}>
              {isAgent
                ? message.agentName || "Agent"
                : isSystem
                  ? "System"
                  : "User"}
            </span>
            <MessageTime timestamp={message.timestamp} fallbackToNow />
          </div>

          <div className="text-sm pt-1">
            {isProcessing ? (
              <ProcessingIndicator
                message={processingMessage || message.content}
                isActive={true}
                agentName={isAgent ? message.agentName || "Agent" : "System"}
              />
            ) : isError ? (
              errorInfo && onRetry ? (
                <ErrorFeedback error={errorInfo} onRetry={onRetry} />
              ) : (
                <ReviewContent content={message.content} />
              )
            ) : isAgent || isSystem ? (
              <ReviewContent content={message.content} />
            ) : (
              <p className="whitespace-pre-wrap break-words break-all">
                {message.content}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
