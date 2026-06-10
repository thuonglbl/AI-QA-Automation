import type { ErrorInfo, ErrorType } from "@/types/pipeline";

/**
 * Error message mapping with 3-part structure:
 * - what: What happened (user-friendly title)
 * - why: Why it happened (plain language explanation)
 * - whatToDo: What to do next (actionable guidance)
 *
 * UX-DR12: No technical jargon, stack traces, or HTTP status codes
 */

export const ERROR_MESSAGES: Record<ErrorType, Omit<ErrorInfo, "type">> = {
  MCP_TIMEOUT: {
    what: "Couldn't retrieve content from Confluence",
    why: "The connection timed out after 30 seconds",
    whatToDo: "Check your network connection and click Retry",
  },
  LLM_FAILURE: {
    what: "AI couldn't process your request",
    why: "The AI service is temporarily unavailable",
    whatToDo: "Wait a moment and click Retry, or try a different AI provider",
  },
  NETWORK_ERROR: {
    what: "Lost connection to the server",
    why: "Your network connection was interrupted",
    whatToDo: "Check your internet connection and click Retry",
  },
  CONFIG_ERROR: {
    what: "Configuration is missing required information",
    why: "Some required settings haven't been provided",
    whatToDo: "Go back to Step 1 and complete the AI provider setup",
  },
  UNKNOWN_ERROR: {
    what: "Something went wrong",
    why: "An unexpected error occurred",
    whatToDo: "Try again or contact support if the problem continues",
  },
};

/**
 * Create a complete ErrorInfo object from an error type
 */
export function createErrorInfo(type: ErrorType): ErrorInfo {
  return {
    type,
    ...ERROR_MESSAGES[type],
  };
}

/**
 * Map backend error codes to frontend error types
 * This abstracts technical backend details from users
 */
export function mapBackendError(backendError: {
  code?: string;
  message?: string;
  type?: string;
}): ErrorInfo {
  // Map backend error codes/patterns to ErrorType
  const code = backendError.code?.toUpperCase() || "";
  const _type = backendError.type?.toUpperCase() || "";
  const message = (backendError.message || "").toLowerCase();

  if (
    code.includes("MCP") ||
    code.includes("TIMEOUT") ||
    message.includes("timeout")
  ) {
    return createErrorInfo("MCP_TIMEOUT");
  }

  if (
    code.includes("LLM") ||
    code.includes("AI") ||
    _type.includes("LLM") ||
    message.includes("ai") ||
    message.includes("language model")
  ) {
    return createErrorInfo("LLM_FAILURE");
  }

  if (
    code.includes("NETWORK") ||
    code.includes("CONNECTION") ||
    message.includes("network") ||
    message.includes("connection")
  ) {
    return createErrorInfo("NETWORK_ERROR");
  }

  if (
    code.includes("CONFIG") ||
    code.includes("MISSING") ||
    message.includes("config") ||
    message.includes("required")
  ) {
    return createErrorInfo("CONFIG_ERROR");
  }

  return createErrorInfo("UNKNOWN_ERROR");
}
