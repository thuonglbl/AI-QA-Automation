import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentMessage } from "@/types/pipeline";

export interface WebSocketState {
  /** Whether WebSocket is connected */
  isConnected: boolean;
  /** Connection error if any */
  error: string | null;
  /** Latest message received (legacy, prefer messageQueue) */
  lastMessage: AgentMessage | null;
  /** Queue of all messages received since last clear */
  messageQueue: AgentMessage[];
}

export interface WebSocketActions {
  /** Send a message to the server */
  sendMessage: (message: unknown) => boolean;
  /** Manually reconnect */
  reconnect: () => void;
  /** Consume a specific number of messages from the queue */
  consumeMessages: (count: number) => void;
  /** Register a handler for raw (non-AgentMessage) WebSocket events */
  onRawEvent: (handler: (data: Record<string, unknown>) => void) => () => void;
}

/** WebSocket URL (Vite proxy handles routing) */
// const WS_URL = "ws://localhost:5173/ws";
const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
const WS_URL = `${wsScheme}://${window.location.host}/ws`;

function buildWsUrl(params: {
  projectId?: string | null;
  threadId?: string | null;
}): string {
  const url = new URL(WS_URL, window.location.origin);
  if (params.projectId) url.searchParams.set("project_id", params.projectId);
  if (params.threadId) url.searchParams.set("threadId", params.threadId);
  // Attach Bearer token so the backend can auth the WebSocket without relying
  // solely on cookies (cookies may be SameSite-blocked in some deployments).
  try {
    const token = localStorage.getItem("aiqa_access_token");
    if (token) {
      url.searchParams.set("token", token);
    }
  } catch {
    // localStorage unavailable (e.g. incognito with storage blocked) — fall back to cookie auth
  }
  return url.toString();
}

/** Reconnection delay in ms */
const RECONNECT_DELAY = 3000;

/** Maximum reconnection attempts */
const MAX_RECONNECT_ATTEMPTS = 5;

/**
 * React hook for WebSocket communication with the backend.
 *
 * Features:
 * - Automatic connection on mount
 * - Automatic reconnection with exponential backoff
 * - Message parsing and type safety
 * - Connection state tracking
 *
 * @returns WebSocket state and actions
 */
export function useWebSocket(params: {
  projectId?: string | null;
  threadId?: string | null;
}): WebSocketState & WebSocketActions {
  const { projectId, threadId } = params;
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<AgentMessage | null>(null);
  const [messageQueue, setMessageQueue] = useState<AgentMessage[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const activeProjectIdRef = useRef(projectId);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const intentionalCloseRef = useRef(false);
  const rawEventHandlersRef = useRef<Set<(data: Record<string, unknown>) => void>>(new Set());

  const activeThreadIdRef = useRef(threadId);

  const getWebSocketCtor = useCallback(() => globalThis.WebSocket, []);

  useEffect(() => {
    activeProjectIdRef.current = projectId;
    activeThreadIdRef.current = threadId;
    setLastMessage(null);
    setMessageQueue([]);
  }, [projectId, threadId]);

  const connect = useCallback(() => {
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Don't create new connection if already connected
    const WebSocketCtor = getWebSocketCtor();
    if (
      wsRef.current?.readyState === WebSocketCtor.OPEN ||
      wsRef.current?.readyState === WebSocketCtor.CONNECTING
    ) {
      return;
    }

    if (!projectId && !threadId) {
      setIsConnected(false);
      setError(null);
      return;
    }

    try {
      const ws = new WebSocketCtor(buildWsUrl({ projectId, threadId }));
      wsRef.current = ws;
      ws.onopen = () => {
        if (wsRef.current && wsRef.current !== ws) return;
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        if (wsRef.current && wsRef.current !== ws) return;
        try {
          const data = JSON.parse(event.data);
          const messageProjectId =
            data.project_id ??
            data.projectId ??
            data.metadata?.project_id ??
            data.metadata?.projectId;
          const messageThreadId =
            data.thread_id ??
            data.threadId ??
            data.metadata?.thread_id ??
            data.metadata?.threadId;

          if (
            messageProjectId &&
            activeProjectIdRef.current &&
            messageProjectId !== activeProjectIdRef.current
          ) {
            return;
          }
          if (
            messageThreadId &&
            activeThreadIdRef.current &&
            messageThreadId !== activeThreadIdRef.current
          ) {
            return;
          }

          // Handle AgentMessage type. Most AgentMessages carry non-empty content,
          // but some are pure-metadata carriers sent with content="" (e.g. Alice's
          // provider_options panel renders entirely from metadata). Keep those when
          // they carry a metadata.type, so the chat can still read their timestamp
          // (the empty-content chat-render filter in App still hides the bubble).
          if (
            data.sender &&
            data.timestamp &&
            (data.content || data.metadata?.type)
          ) {
            const agentMsg = data as AgentMessage;
            setLastMessage(agentMsg);
            setMessageQueue((prev) => [...prev, agentMsg]);
          }

          // Handle other message types (ack, error)
          if (data.type === "error") {
            console.error("WebSocket error message:", data.message);
          }

          // Notify raw event handlers for non-AgentMessage types (e.g. artifact_change)
          if (data.type && data.type !== "auth_status" && data.type !== "ack" && data.type !== "error") {
            if (!data.sender || !data.content || !data.timestamp) {
              // Not an AgentMessage — dispatch to raw handlers
              for (const handler of rawEventHandlersRef.current) {
                try {
                  handler(data as Record<string, unknown>);
                } catch (err) {
                  console.error("Raw event handler error:", err);
                }
              }
            }
          }
        } catch (parseError) {
          console.error("Failed to parse WebSocket message:", parseError);
        }
      };

      ws.onerror = () => {
        if (wsRef.current && wsRef.current !== ws) return;
        console.error("WebSocket error");
        setError("WebSocket connection error");
      };

      ws.onclose = (event) => {
        if (wsRef.current && wsRef.current !== ws) return;
        console.log("WebSocket closed, code:", event.code);
        setIsConnected(false);
        wsRef.current = null;

        // WS close code 4401 = server-side Unauthorized (session expired/missing).
        // Dispatch auth-error so AuthContext can refresh and redirect to login.
        // Do NOT attempt reconnect — that would loop forever.
        if (event.code === 4401) {
          console.warn(
            "WebSocket closed with 4401 — session expired or invalid",
          );
          window.dispatchEvent(new Event("auth-error"));
          return;
        }

        // Skip reconnection if intentionally closed (unmount or manual reconnect)
        if (intentionalCloseRef.current) {
          return;
        }

        // Attempt reconnection with exponential backoff
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++;
          const delay =
            RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current - 1);
          console.log(
            `Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`,
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          setError("Maximum reconnection attempts reached");
        }
      };
    } catch (err) {
      setError(`Failed to create WebSocket: ${err}`);
    }
  }, [getWebSocketCtor, projectId, threadId]);

  const sendMessage = useCallback(
    (message: unknown): boolean => {
      const ws = wsRef.current;
      const WebSocketCtor = getWebSocketCtor();
      if (
        ws &&
        ws.readyState === WebSocketCtor.OPEN &&
        (projectId || threadId)
      ) {
        let payload = message as any;
        if (typeof message === "object" && message !== null) {
          payload = { ...message };
          if (projectId) {
            payload.projectId = projectId;
            payload.project_id = projectId;
          }
          if (threadId) {
            payload.threadId = threadId;
            payload.thread_id = threadId;
          }
        }
        ws.send(JSON.stringify(payload));
        return true;
      } else {
        console.warn(
          "WebSocket not connected.",
          "ws present:", !!ws,
          "readyState:", ws?.readyState,
          "expected OPEN:", getWebSocketCtor().OPEN,
          "projectId:", projectId,
          "threadId:", threadId
        );
        return false;
      }
    },
    [getWebSocketCtor, projectId, threadId],
  );

  const consumeMessages = useCallback((count: number) => {
    setMessageQueue((prev) => prev.slice(count));
  }, []);

  const onRawEvent = useCallback(
    (handler: (data: Record<string, unknown>) => void) => {
      rawEventHandlersRef.current.add(handler);
      return () => {
        rawEventHandlersRef.current.delete(handler);
      };
    },
    [],
  );

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    intentionalCloseRef.current = true;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    intentionalCloseRef.current = false;
    connect();
  }, [connect]);

  useEffect(() => {
    intentionalCloseRef.current = true;
    wsRef.current?.close();
    wsRef.current = null;
    intentionalCloseRef.current = false;
    setIsConnected(false);

    if (!projectId && !threadId) {
      setError(null);
      return;
    }

    connect();

    return () => {
      intentionalCloseRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
      intentionalCloseRef.current = false;
    };
  }, [connect, projectId, threadId]);

  return {
    isConnected,
    error,
    lastMessage,
    messageQueue,
    sendMessage,
    reconnect,
    consumeMessages,
    onRawEvent,
  };
}
