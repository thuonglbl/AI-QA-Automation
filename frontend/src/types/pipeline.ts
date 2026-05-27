/** Pipeline step numbers (1-5) */
export type PipelineStep = 1 | 2 | 3 | 4 | 5;

/** Agent names */
export type AgentName = "Alice" | "Bob" | "Mary" | "Sarah" | "Jack";

/** Agent status states */
export type AgentStatus =
  | "start" // Initial state, waiting for user input
  | "processing" // Agent is working
  | "review_request" // Agent needs user approval
  | "done" // Step completed, ready to continue
  | "completed" // Final step completed (step 5 only)
  | "error"; // Pipeline encountered an error

/** Message sender type */
export type MessageSender = "agent" | "user" | "system";

/** Agent message structure (matches backend AgentMessage model) */
export interface AgentMessage {
  /** Unique message ID */
  id: string;
  /** Message sender */
  sender: MessageSender;
  /** Agent name (if sender is "agent") */
  agentName?: AgentName;
  /** Message content (markdown supported) */
  content: string;
  /** ISO 8601 timestamp */
  timestamp: string;
  /** Message type for styling */
  messageType: "text" | "code" | "error" | "success" | "warning" | "info" | "processing";
  /** Optional metadata */
  metadata?: Record<string, unknown>;
}

/** Pipeline state for UI */
export interface PipelineState {
  /** Current step (1-5) */
  currentStep: PipelineStep;
  /** Current agent status */
  status: AgentStatus;
  /** Active agent for current step */
  currentAgent: AgentName;
  /** Chat messages for current step */
  messages: AgentMessage[];
  /** Whether user has scrolled up (for new message indicator) */
  hasScrolledUp: boolean;
  /** Processing status message */
  processingMessage?: string;
  /** Error message if any */
  error?: string;
}

/** Start request payload */
export interface StartRequest {
  step: PipelineStep;
  inputData: Record<string, unknown>;
}

/** Approve request payload */
export interface ApproveRequest {
  step: PipelineStep;
  itemIndex?: number;
}

/** Reject request payload */
export interface RejectRequest {
  step: PipelineStep;
  feedback: string;
  itemIndex?: number;
}

/** Continue request payload */
export interface ContinueRequest {
  fromStep: PipelineStep;
}

/** Action response from backend */
export interface ActionResponse {
  success: boolean;
  message: string;
  currentStep: PipelineStep;
  status: AgentStatus;
}

/** Error types for error feedback */
export type ErrorType =
  | 'MCP_TIMEOUT'
  | 'LLM_FAILURE'
  | 'NETWORK_ERROR'
  | 'CONFIG_ERROR'
  | 'UNKNOWN_ERROR';

/** Error info with 3-part structure (what, why, whatToDo) */
export interface ErrorInfo {
  type: ErrorType;
  what: string;
  why: string;
  whatToDo: string;
}

/** ProcessingIndicator component props */
export interface ProcessingIndicatorProps {
  message: string;
  isActive?: boolean;
  className?: string;
}

/** ErrorFeedback component props */
export interface ErrorFeedbackProps {
  error: ErrorInfo;
  onRetry: () => void;
  className?: string;
}

/** Agent configuration */
export interface AgentConfig {
  name: AgentName;
  displayName: string;
  stepNumber: PipelineStep;
  stepTitle: string;
  color: string;
  avatar: string;
  inputConfig?: {
    fields: InputFieldConfig[];
  };
}

/** Input field configuration for ChatInputArea */
export interface InputFieldConfig {
  name: string;
  label: string;
  type: 'text' | 'url' | 'password' | 'textarea';
  placeholder?: string;
  required?: boolean;
  validation?: (value: string) => string | null;
}

/** ChatInputArea component props */
export interface ChatInputAreaProps {
  state: 'start' | 'processing' | 'review' | 'reject_feedback' | 'done';
  stepNumber: number;
  isLastStep: boolean;
  inputConfig?: {
    fields: InputFieldConfig[];
  };
  disabledReason?: string;
  isLoading?: boolean;
  onStart: (values: Record<string, string>) => void;
  onApprove: () => void;
  onReject: () => void;
  onSubmitFeedback: (feedback: string) => void;
  onContinue: () => void;
  // Per-item review navigation (for Mary's test case review)
  currentIndex?: number;
  totalCount?: number;
  onNext?: () => void;
  onPrevious?: () => void;
}

/** Static agent configurations */
export const AGENTS: Record<AgentName, AgentConfig> = {
  Alice: {
    name: "Alice",
    displayName: "Alice",
    stepNumber: 1,
    stepTitle: "AI Provider Configuration",
    color: "#EC4899",
    avatar: "A",
  },
  Bob: {
    name: "Bob",
    displayName: "Bob",
    stepNumber: 2,
    stepTitle: "Requirements Extraction",
    color: "#3B82F6",
    avatar: "B",
    inputConfig: {
      fields: [
        {
          name: "confluence_url",
          label: "Confluence Project URL",
          type: "url",
          placeholder: "https://company.atlassian.net/wiki/spaces/TEST",
          required: true,
        },
        {
          name: "jira_url",
          label: "Jira URL (Optional)",
          type: "url",
          placeholder: "https://company.atlassian.net/jira/software/c/projects/TEST",
          required: false,
        },
        {
          name: "mcp_pat",
          label: "MCP Personal Access Token",
          type: "password",
          placeholder: "Enter token (saved locally)",
          required: true,
        }
      ]
    }
  },
  Mary: {
    name: "Mary",
    displayName: "Mary",
    stepNumber: 3,
    stepTitle: "Test Case Generation",
    color: "#22C55E",
    avatar: "M",
  },
  Sarah: {
    name: "Sarah",
    displayName: "Sarah",
    stepNumber: 4,
    stepTitle: "Test Script Generation",
    color: "#A855F7",
    avatar: "S",
  },
  Jack: {
    name: "Jack",
    displayName: "Jack",
    stepNumber: 5,
    stepTitle: "Test Execution",
    color: "#F97316",
    avatar: "J",
  },
};
