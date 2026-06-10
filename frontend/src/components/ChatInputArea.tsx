import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Label } from "@/components/ui/label";
import type { ChatInputAreaProps } from "@/types/pipeline";
import {
  Loader2,
  Check,
  X,
  ArrowRight,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

export function ChatInputArea({
  state,
  stepNumber,
  isLastStep,
  inputConfig,
  disabledReason,
  isLoading = false,
  onStart,
  onApprove,
  onReject,
  onSubmitFeedback,
  onContinue,
  currentIndex,
  totalCount,
  onNext,
  onPrevious,
}: ChatInputAreaProps) {
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState("");
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});

  const primaryButtonRef = useRef<HTMLButtonElement>(null);
  const feedbackTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus primary action when state changes (AC 9)
  useEffect(() => {
    if (
      state === "start" ||
      state === "review" ||
      state === "reject_feedback" ||
      state === "done"
    ) {
      // Small delay to ensure DOM is ready
      const timer = setTimeout(() => {
        primaryButtonRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [state]);

  // Auto-focus feedback textarea when entering reject_feedback state (AC 5)
  useEffect(() => {
    if (state === "reject_feedback") {
      const timer = setTimeout(() => {
        feedbackTextareaRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [state]);

  // Reset input values when entering start state
  useEffect(() => {
    if (state === "start") {
      const initialValues: Record<string, string> = {};

      // Auto-load values from localStorage for certain fields
      if (inputConfig?.fields) {
        inputConfig.fields.forEach((field) => {
          if (field.name === "mcp_pat") {
            const savedToken = localStorage.getItem("mcp_pat");
            if (savedToken) {
              initialValues[field.name] = savedToken;
            }
          }
        });
      }

      setInputValues(initialValues);
      setValidationErrors({});
    }
  }, [state, stepNumber, inputConfig]);

  // Reset feedback when leaving reject_feedback state
  useEffect(() => {
    if (state !== "reject_feedback") {
      setFeedback("");
    }
  }, [state]);

  const handleInputChange = useCallback(
    (fieldName: string, value: string) => {
      setInputValues((prev) => ({ ...prev, [fieldName]: value }));
      // Clear validation error when user types
      if (validationErrors[fieldName]) {
        setValidationErrors((prev) => ({ ...prev, [fieldName]: "" }));
      }
    },
    [validationErrors],
  );

  const validateInputs = useCallback((): boolean => {
    if (!inputConfig?.fields) return true;

    const errors: Record<string, string> = {};
    let isValid = true;

    for (const field of inputConfig.fields) {
      const value = inputValues[field.name] || "";

      // Check required
      if (field.required && !value.trim()) {
        errors[field.name] = `${field.label} is required`;
        isValid = false;
        continue;
      }

      // Run custom validation if provided
      if (field.validation && value.trim()) {
        const error = field.validation(value);
        if (error) {
          errors[field.name] = error;
          isValid = false;
        }
      }
    }

    setValidationErrors(errors);
    return isValid;
  }, [inputConfig, inputValues]);

  const handleStart = useCallback(() => {
    if (validateInputs()) {
      // Save specific values to local storage
      if (inputValues.mcp_pat) {
        localStorage.setItem("mcp_pat", inputValues.mcp_pat);
      }
      onStart(inputValues);
    }
  }, [inputValues, onStart, validateInputs]);

  const handleSubmitFeedback = useCallback(() => {
    if (feedback.trim()) {
      onSubmitFeedback(feedback);
    }
  }, [feedback, onSubmitFeedback]);

  // Check if start button should be disabled
  const canStart =
    inputConfig?.fields.every((field) => {
      if (!field.required) return true;
      return (inputValues[field.name] || "").trim().length > 0;
    }) ?? true;

  // Render Start State (AC 1, 7)
  const renderStartState = () => {
    return (
      <div className="space-y-4 animate-slide-up" aria-live="polite">
        {inputConfig?.fields.map((field) => (
          <div key={field.name} className="space-y-2">
            <Label htmlFor={field.name} className="text-sm font-medium">
              {field.label}
              {field.required && (
                <span className="text-destructive ml-1">*</span>
              )}
            </Label>
            {field.type === "textarea" ? (
              <Textarea
                id={field.name}
                placeholder={field.placeholder}
                value={inputValues[field.name] || ""}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={cn(
                  "min-h-[100px]",
                  validationErrors[field.name] && "border-destructive",
                )}
                aria-invalid={!!validationErrors[field.name]}
                aria-describedby={
                  validationErrors[field.name]
                    ? `${field.name}-error`
                    : undefined
                }
              />
            ) : (
              <Input
                id={field.name}
                type={field.type}
                placeholder={field.placeholder}
                value={inputValues[field.name] || ""}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={cn(
                  validationErrors[field.name] && "border-destructive",
                )}
                aria-invalid={!!validationErrors[field.name]}
                aria-describedby={
                  validationErrors[field.name]
                    ? `${field.name}-error`
                    : undefined
                }
              />
            )}
            {validationErrors[field.name] && (
              <p
                id={`${field.name}-error`}
                className="text-sm text-destructive"
              >
                {validationErrors[field.name]}
              </p>
            )}
          </div>
        ))}

        <div className="flex justify-end pt-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    ref={primaryButtonRef}
                    onClick={handleStart}
                    disabled={!canStart || isLoading}
                    className="bg-blue-500 hover:bg-blue-600 text-white min-w-[100px]"
                    aria-label="Start processing"
                  >
                    {isLoading ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : null}
                    Start
                  </Button>
                </span>
              </TooltipTrigger>
              {!canStart && (
                <TooltipContent side="top">
                  <p>
                    {disabledReason || "Enter required information to start"}
                  </p>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    );
  };

  // Render Processing State (AC 2)
  const renderProcessingState = () => {
    return (
      <div
        className="flex items-center justify-center p-6 rounded-lg bg-surface-100 border border-surface-200 animate-slide-up"
        aria-live="polite"
      >
        <div className="flex items-center gap-3 text-surface-600">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="font-medium">Agent is working...</span>
        </div>
      </div>
    );
  };

  // Render Review State (AC 3, 6, 8)
  const renderReviewState = () => {
    const hasNavigation =
      currentIndex !== undefined && totalCount !== undefined && totalCount > 1;
    const canGoPrevious = hasNavigation && currentIndex > 0;
    const canGoNext = hasNavigation && currentIndex < totalCount - 1;

    return (
      <div className="flex flex-col gap-3 animate-slide-up" aria-live="polite">
        {/* Navigation bar for per-item review (UX-DR14) */}
        {hasNavigation && (
          <div className="flex items-center justify-between px-4 py-2 bg-slate-50 rounded-lg border border-slate-200">
            <Button
              variant="outline"
              size="sm"
              onClick={onPrevious}
              disabled={!canGoPrevious}
              className="flex items-center gap-1"
              aria-label="Previous item"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <span className="text-sm font-medium text-slate-700">
              {currentIndex + 1} of {totalCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={onNext}
              disabled={!canGoNext}
              className="flex items-center gap-1"
              aria-label="Next item"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-between gap-3">
          {/* Reject button - secondary, left (AC 6) */}
          <Button
            variant="outline"
            onClick={onReject}
            className="border-red-500 text-red-500 hover:bg-red-50 hover:text-red-600 min-w-[100px]"
            aria-label="Reject and provide feedback"
          >
            <X className="w-4 h-4 mr-2" />
            Reject
          </Button>

          {/* Approve button - primary, right (AC 6) */}
          <Button
            ref={primaryButtonRef}
            onClick={onApprove}
            className="bg-green-500 hover:bg-green-600 text-white min-w-[100px]"
            aria-label="Approve and continue"
          >
            <Check className="w-4 h-4 mr-2" />
            Approve
          </Button>
        </div>
      </div>
    );
  };

  // Render Reject Feedback State (AC 4, 5)
  const renderRejectFeedbackState = () => {
    return (
      <div className="space-y-4 animate-slide-up" aria-live="polite">
        <div className="space-y-2">
          <Label htmlFor="feedback" className="text-sm font-medium">
            Please explain what needs to be corrected
          </Label>
          <Textarea
            ref={feedbackTextareaRef}
            id="feedback"
            placeholder="Describe what needs to be changed or corrected..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            className="min-h-[120px]"
            maxLength={1000}
          />
          <div className="flex justify-between text-xs text-surface-500">
            <span>Your feedback will help improve the output</span>
            <span>{feedback.length}/1000</span>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            ref={primaryButtonRef}
            onClick={handleSubmitFeedback}
            disabled={!feedback.trim() || isLoading}
            className="bg-blue-500 hover:bg-blue-600 text-white min-w-[100px]"
            aria-label="Submit feedback"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : null}
            Submit
          </Button>
        </div>
      </div>
    );
  };

  // Render Done State (AC 5)
  const renderDoneState = () => {
    const isFinalStep = isLastStep && stepNumber === 5;

    return (
      <div className="flex justify-end animate-slide-up" aria-live="polite">
        <Button
          ref={primaryButtonRef}
          onClick={onContinue}
          disabled={isLoading}
          className={cn(
            "min-w-[120px]",
            isFinalStep
              ? "bg-green-500 hover:bg-green-600 text-white"
              : "bg-blue-500 hover:bg-blue-600 text-white",
          )}
          aria-label={
            isFinalStep ? "Complete workflow" : "Continue to next step"
          }
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : isFinalStep ? (
            <>
              <CheckCircle className="w-4 h-4 mr-2" />
              Completed
            </>
          ) : (
            <>
              Continue
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          )}
        </Button>
      </div>
    );
  };

  // Render based on state
  const renderContent = () => {
    switch (state) {
      case "start":
        return renderStartState();
      case "processing":
        return renderProcessingState();
      case "review":
        return renderReviewState();
      case "reject_feedback":
        return renderRejectFeedbackState();
      case "done":
        return renderDoneState();
      default:
        return null;
    }
  };

  return (
    <div className="p-4 bg-white border-t border-surface-200">
      <div className="transition-all duration-150 ease-in-out">
        {renderContent()}
      </div>
    </div>
  );
}

export default ChatInputArea;
