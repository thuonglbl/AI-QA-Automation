import { useState, useCallback, useEffect, useRef } from "react";
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
  addUserMessage: (
    content: string,
    messageType?: AgentMessage["messageType"],
    metadata?: any,
  ) => void;
  reset: () => void;
  setError: (error: string | undefined) => void;
  clearHistory: () => void;
}

// API client for conversation persistence
// using apiFetch from @/lib/api

async function loadConversationFromAPI(params: {
  projectId: string | null;
  threadId: string | null;
}): Promise<Partial<PipelineState> | null | "denied"> {
  const { projectId, threadId } = params;
  try {
    if (threadId) {
      const data = await apiFetch<any>(`/threads/${threadId}`);
      
      const stepToAgent: Record<number, AgentName> = {
        1: "Alice",
        2: "Bob",
        3: "Mary",
        4: "Sarah",
        5: "Jack",
      };
      const currentAgent = stepToAgent[data.current_step || 1] || "Alice";
      
      // Map basic messages. Note: frontend-specific metadata might be lost
      // if not stored in the new Message model.
      const messages = (data.messages || []).map((m: any) => ({
        id: m.id,
        sender: m.role === "user" ? "user" : "agent",
        agentName: m.role !== "user" ? currentAgent : undefined,
        content: m.content,
        timestamp: m.created_at || new Date().toISOString(),
        messageType: "text",
      }));

      // Find the latest agent run to populate processing state if any
      const latestRun = data.agent_runs?.length > 0 
        ? data.agent_runs[data.agent_runs.length - 1] 
        : null;
        
      if (latestRun && latestRun.status === "completed" && latestRun.summary) {
        messages.push({
          id: latestRun.id,
          sender: "system",
          content: latestRun.summary,
          timestamp: latestRun.updated_at || latestRun.created_at,
          messageType: "success",
        });
      }

      return {
        currentStep: data.current_step || 1,
        status: (data.status as AgentStatus) || "start",
        currentAgent,
        messages,
      };
    } else {
      const url = `/projects/${projectId}/conversation`;
      const data = await apiFetch<any>(url);
      return {
        currentStep: data.current_step,
        status: data.status as AgentStatus,
        currentAgent: data.current_agent as AgentName,
        messages:
          data.messages?.map((m: Record<string, unknown>) => ({
            id: m.id,
            sender: m.sender,
            agentName: m.agent_name,
            content: m.content,
            timestamp: m.timestamp,
            messageType: m.message_type,
            metadata: m.metadata,
          })) || [],
      };
    }
  } catch (error) {
    if (error instanceof ApiError) {
      // Thread-scoped access loss (e.g. project membership was revoked, or the
      // thread no longer exists) returns 403/404. Signal a recoverable denial
      // so the caller can clear the stale thread id without a global logout.
      // Auth (401) errors are intentionally left to the global auth handler.
      if (threadId && (error.kind === "forbidden" || error.kind === "not_found")) {
        return "denied";
      }
      if (
        error.kind === "auth" ||
        error.kind === "forbidden" ||
        error.status === 404
      ) {
        return null;
      }
    }
    console.error("Failed to load conversation from API:", error);
    return null;
  }
}

async function saveConversationToAPI(
  params: { projectId: string | null; threadId: string | null },
  state: PipelineState,
): Promise<boolean> {
  const { projectId, threadId } = params;
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

    const url = threadId
      ? `/threads/${threadId}/conversation`
      : `/projects/${projectId}/conversation`;
    await apiFetch(url, {
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
export function usePipelineState(params: {
  projectId: string | null;
  threadId: string | null;
  onThreadDenied?: (threadId: string) => void;
}): PipelineStateSelectors & PipelineStateActions {
  const { projectId, threadId, onThreadDenied } = params;
  const [state, setState] = useState<PipelineState>(initialState);
  const [isLoaded, setIsLoaded] = useState(false);
  // Keep the latest handler in a ref so the load effect doesn't re-run (and
  // re-fetch) whenever the caller passes a new callback identity.
  const onThreadDeniedRef = useRef(onThreadDenied);
  onThreadDeniedRef.current = onThreadDenied;

  // Load conversation from API on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoaded(false);
      if (!projectId && !threadId) {
        setIsLoaded(true);
        return;
      }
      const saved = await loadConversationFromAPI({ projectId, threadId });
      if (cancelled) {
        return;
      }
      if (saved === "denied") {
        // Access to this thread was revoked. Surface it so App can drop the
        // stale thread id and prompt recovery; don't hydrate any state.
        if (threadId) {
          onThreadDeniedRef.current?.(threadId);
        }
        setIsLoaded(true);
        return;
      }
      if (saved) {
        let filteredMessages = saved.messages || [];
        const isAliceStart =
          (saved.status === "error" || saved.status === "start") &&
          saved.currentStep === 1;

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
              (m: AgentMessage) =>
                !(
                  m.agentName === "Alice" &&
                  (m.messageType === "error" || m.messageType === "success")
                ),
            );
          }
        }

        setState((prev) => ({
          ...prev,
          currentStep: saved.currentStep || prev.currentStep,
          status: isAliceStart ? "start" : saved.status || prev.status,
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
  }, [projectId, threadId]);

  // Persist state to API whenever it changes (debounced)
  useEffect(() => {
    if (!isLoaded || (!projectId && !threadId)) return; // Don't save until initial load is complete and projectId or threadId is present

    const timeoutId = setTimeout(() => {
      saveConversationToAPI({ projectId, threadId }, state);
    }, 500); // Debounce 500ms

    return () => clearTimeout(timeoutId);
  }, [state, isLoaded, projectId, threadId]);

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
        newState.processingMessage = message.metadata
          .processingMessage as string;
      }

      return newState;
    });
  }, []);

  // Add a user message to the conversation history
  const addUserMessage = useCallback(
    (
      content: string,
      messageType: AgentMessage["messageType"] = "text",
      metadata?: any,
    ) => {
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
    },
    [],
  );

  const reset = useCallback(() => {
    setState({
      currentStep: 1,
      status: "start",
      currentAgent: "Alice",
      messages: [],
      hasScrolledUp: false,
    });
    // Also clear on server (fire and forget)
    if (projectId || threadId) {
      saveConversationToAPI(
        { projectId, threadId },
        {
          currentStep: 1,
          status: "start",
          currentAgent: "Alice",
          messages: [],
          hasScrolledUp: false,
        },
      );
    }
  }, [projectId, threadId]);

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
