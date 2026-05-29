import { useState, useCallback, useEffect } from "react";
import { apiFetch, ApiError } from "@/lib/api";
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
  addUserMessage: (content: string, messageType?: AgentMessage["messageType"], metadata?: any) => void;
  reset: () => void;
  setError: (error: string | undefined) => void;
  clearHistory: () => void;
}

// API client for conversation persistence
// using apiFetch from @/lib/api

async function loadConversationFromAPI(projectId: string): Promise<Partial<PipelineState> | null> {
  try {
    const data = await apiFetch<any>(`/projects/${projectId}/conversation`);
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
    // Silently ignore auth errors (expected when not logged in yet)
    if (error instanceof ApiError && (error.kind === "auth" || error.kind === "forbidden")) {
      return null;
    }
    console.error("Failed to load conversation from API:", error);
    return null;
  }
}

async function saveConversationToAPI(projectId: string, state: PipelineState): Promise<boolean> {
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

    await apiFetch(`/projects/${projectId}/conversation`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

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
export function usePipelineState(projectId: string | null): PipelineStateSelectors & PipelineStateActions {
  const [state, setState] = useState<PipelineState>(initialState);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load conversation from API on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoaded(false);
      if (!projectId) {
        setIsLoaded(true);
        return;
      }
      const saved = await loadConversationFromAPI(projectId);
      if (!cancelled && saved) {
        let filteredMessages = saved.messages || [];
        const isAliceStart = (saved.status === "error" || saved.status === "start") && saved.currentStep === 1;
        
        if (isAliceStart) {
          // Find the last provider_options message by searching backwards
          let lastOptionsIndex = -1;
          for (let i = filteredMessages.length - 1; i >= 0; i--) {
            const msg = filteredMessages[i];
            if (msg && msg.metadata?.type === "provider_options") {
              lastOptionsIndex = i;
              break;
            }
          }
          
          if (lastOptionsIndex >= 0) {
            // Keep only up to the provider_options message, discarding any failed connection attempts
            filteredMessages = filteredMessages.slice(0, lastOptionsIndex + 1);
          } else {
            // Fallback filter
            filteredMessages = filteredMessages.filter(
              (m: AgentMessage) => !(m.agentName === 'Alice' && (m.messageType === 'error' || m.messageType === 'success'))
            );
          }
        }

        setState((prev) => ({
          ...prev,
          currentStep: saved.currentStep || prev.currentStep,
          status: isAliceStart ? "start" : (saved.status || prev.status),
          currentAgent: saved.currentAgent || prev.currentAgent,
          messages: filteredMessages,
        }));
      }
      setIsLoaded(true);
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Persist state to API whenever it changes (debounced)
  useEffect(() => {
    if (!isLoaded || !projectId) return; // Don't save until initial load is complete and projectId is present

    const timeoutId = setTimeout(() => {
      saveConversationToAPI(projectId, state);
    }, 500); // Debounce 500ms

    return () => clearTimeout(timeoutId);
  }, [state, isLoaded, projectId]);

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
  const addUserMessage = useCallback((content: string, messageType: AgentMessage["messageType"] = "text", metadata?: any) => {
    const userMessage: AgentMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      sender: "user",
      content,
      timestamp: new Date().toISOString(),
      messageType,
      metadata,
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
    if (projectId) {
      saveConversationToAPI(projectId, {
        currentStep: 1,
        status: "start",
        currentAgent: "Alice",
        messages: [],
        hasScrolledUp: false,
      });
    }
  }, [projectId]);

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
