import { Button } from "@/components/ui/button";
import { AlertCircle, RefreshCw } from "lucide-react";
import type { ErrorFeedbackProps } from "@/types/pipeline";
import { cn } from "@/lib/utils";

export function ErrorFeedback({
  error,
  onRetry,
  className,
}: ErrorFeedbackProps) {
  return (
    <div role="alert" className={cn("flex flex-col gap-3", className)}>
      {/* Error icon and title (What happened) */}
      <div className="flex items-start gap-2">
        <AlertCircle
          className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <div className="flex flex-col gap-1">
          <h4 className="text-sm font-semibold text-red-700">{error.what}</h4>
        </div>
      </div>

      {/* Explanation (Why it happened) */}
      <p className="text-sm text-slate-600 pl-7">{error.why}</p>

      {/* Action guidance (What to do) */}
      <p className="text-sm text-slate-700 font-medium pl-7">
        {error.whatToDo}
      </p>

      {/* Retry button */}
      <div className="pl-7 pt-1">
        <Button
          onClick={onRetry}
          size="sm"
          className="gap-2 bg-blue-500 hover:bg-blue-600 text-white"
          autoFocus
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          <span>Retry this action</span>
        </Button>
      </div>

      {/* Screen reader only error type */}
      <span className="sr-only">Error type: {error.type}</span>
    </div>
  );
}
