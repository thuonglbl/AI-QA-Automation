import { useState, useCallback } from "react";
import type {
  AgentMessage,
  AgentName,
  AgentStatus,
  PipelineState,
  PipelineStep,
} from "@/types/pipeline";
import { AGENTS } from "@/types/pipeline";

export interface PipelineStateSelectors {
  currentStep: PipelineStep;
  currentAgent: AgentName;
  agentConfig: (typeof AGENTS)[AgentName];
  status: AgentStatus;
  completedSteps: number;
  messages: AgentMessage[];
  processingMessage?: string;
  error?: string;
}

export interface PipelineStateActions {
  updateFromMessage: (message: AgentMessage) => void;
  reset: () => void;
  setError: (error: string | undefined) => void;
}

const initialState: PipelineState = {
  currentStep: 1,
  status: "start",
  currentAgent: "Alice",
  messages: [],
  hasScrolledUp: false,
};

/**
 * React hook for managing pipeline state derived from WebSocket messages.
 *
 * Features:
 * - Tracks current step and agent
 * - Manages agent status transitions
 * - Calculates completed steps
 * - Stores chat messages per step
 *
 * @returns Pipeline state selectors and actions
 */
export function usePipelineState(): PipelineStateSelectors & PipelineStateActions {
  const [state, setState] = useState<PipelineState>(initialState);

  const updateFromMessage = useCallback((message: AgentMessage) => {
    setState((prev) => {
      const newState = { ...prev };

      // Add message to history
      newState.messages = [...prev.messages, message];

      // Update agent and step from message metadata
      if (message.metadata?.state) {
        newState.status = message.metadata.state as AgentStatus;
      }

      if (message.agentName) {
        newState.currentAgent = message.agentName;
        newState.currentStep = AGENTS[message.agentName].stepNumber;
      }

      // Extract processing message if present
      if (message.metadata?.processingMessage) {
        newState.processingMessage = message.metadata.processingMessage as string;
      }

      return newState;
    });
  }, []);

  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  const setErrorState = useCallback((error: string | undefined) => {
    setState((prev) => ({ ...prev, error }));
  }, []);

  // Calculate completed steps based on status and current step
  const completedSteps = (() => {
    if (state.status === "completed") {
      return 5;
    }
    if (state.status === "done") {
      return state.currentStep;
    }
    // For other states, completed steps are previous steps
    return Math.max(0, state.currentStep - 1);
  })();

  return {
    currentStep: state.currentStep,
    currentAgent: state.currentAgent,
    agentConfig: AGENTS[state.currentAgent],
    status: state.status,
    completedSteps,
    messages: state.messages,
    processingMessage: state.processingMessage,
    error: state.error,
    updateFromMessage,
    reset,
    setError: setErrorState,
  };
}
