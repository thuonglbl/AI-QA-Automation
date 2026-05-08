import { useState, useCallback, useEffect } from "react";
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
  isLoaded: boolean;
}

export interface PipelineStateActions {
  updateFromMessage: (message: AgentMessage) => void;
  addUserMessage: (content: string, messageType?: AgentMessage["messageType"]) => void;
  reset: () => void;
  setError: (error: string | undefined) => void;
  clearHistory: () => void;
}

// API client for conversation persistence
const API_BASE = "/api";

async function loadConversationFromAPI(): Promise<Partial<PipelineState> | null> {
  try {
    const response = await fetch(`${API_BASE}/conversation`);
    if (!response.ok) {
      if (response.status === 401) return null; // Not authenticated
      throw new Error(`Failed to load conversation: ${response.status}`);
    }
    const data = await response.json();
    return {
      currentStep: data.current_step,
      status: data.status as AgentStatus,
      currentAgent: data.current_agent as AgentName,
      messages: data.messages?.map((m: Record<string, unknown>) => ({
        id: m.id,
        sender: m.sender,
        agentName: m.agent_name,
        content: m.content,
        timestamp: m.timestamp,
        messageType: m.message_type,
        metadata: m.metadata,
      })) || [],
    };
  } catch (error) {
    console.error("Failed to load conversation from API:", error);
    return null;
  }
}

async function saveConversationToAPI(state: PipelineState): Promise<boolean> {
  try {
    const payload = {
      conversation: {
        messages: state.messages.map((m) => ({
          id: m.id,
          sender: m.sender,
          agent_name: m.agentName,
          content: m.content,
          timestamp: m.timestamp,
          message_type: m.messageType,
          metadata: m.metadata,
        })),
        current_step: state.currentStep,
        status: state.status,
        current_agent: state.currentAgent,
        updated_at: new Date().toISOString(),
      },
    };

    const response = await fetch(`${API_BASE}/conversation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to save conversation: ${response.status}`);
    }
    return true;
  } catch (error) {
    console.error("Failed to save conversation to API:", error);
    return false;
  }
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
  const [isLoaded, setIsLoaded] = useState(false);

  // Load conversation from API on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      const saved = await loadConversationFromAPI();
      if (!cancelled && saved) {
        setState((prev) => ({
          ...prev,
          currentStep: saved.currentStep || prev.currentStep,
          status: saved.status || prev.status,
          currentAgent: saved.currentAgent || prev.currentAgent,
          messages: saved.messages || prev.messages,
        }));
      }
      setIsLoaded(true);
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  // Persist state to API whenever it changes (debounced)
  useEffect(() => {
    if (!isLoaded) return; // Don't save until initial load is complete

    const timeoutId = setTimeout(() => {
      saveConversationToAPI(state);
    }, 500); // Debounce 500ms

    return () => clearTimeout(timeoutId);
  }, [state, isLoaded]);

  const updateFromMessage = useCallback((message: AgentMessage) => {
    setState((prev) => {
      const newState = { ...prev };

      // Add message to history (avoid duplicates based on id)
      const exists = prev.messages.some((m) => m.id === message.id);
      if (!exists) {
        newState.messages = [...prev.messages, message];
      }

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

  // Add a user message to the conversation history
  const addUserMessage = useCallback((content: string, messageType: AgentMessage["messageType"] = "text") => {
    const userMessage: AgentMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      sender: "user",
      content,
      timestamp: new Date().toISOString(),
      messageType,
    };
    setState((prev) => ({
      ...prev,
      messages: [...prev.messages, userMessage],
    }));
  }, []);

  const reset = useCallback(() => {
    setState({
      currentStep: 1,
      status: "start",
      currentAgent: "Alice",
      messages: [],
      hasScrolledUp: false,
    });
    // Also clear on server (fire and forget)
    saveConversationToAPI({
      currentStep: 1,
      status: "start",
      currentAgent: "Alice",
      messages: [],
      hasScrolledUp: false,
    });
  }, []);

  const clearHistory = useCallback(() => {
    setState((prev) => ({
      ...prev,
      messages: [],
    }));
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
    isLoaded,
    updateFromMessage,
    addUserMessage,
    reset,
    setError: setErrorState,
    clearHistory,
  };
}
