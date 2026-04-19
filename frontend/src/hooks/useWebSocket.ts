import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentMessage } from "@/types/pipeline";

export interface WebSocketState {
  /** Whether WebSocket is connected */
  isConnected: boolean;
  /** Connection error if any */
  error: string | null;
  /** Latest message received */
  lastMessage: AgentMessage | null;
}

export interface WebSocketActions {
  /** Send a message to the server */
  sendMessage: (message: unknown) => void;
  /** Manually reconnect */
  reconnect: () => void;
}

/** WebSocket URL (Vite proxy handles routing) */
const WS_URL = "ws://localhost:5173/ws";

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
export function useWebSocket(): WebSocketState & WebSocketActions {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<AgentMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);

  const connect = useCallback(() => {
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected");
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle AgentMessage type
          if (data.sender && data.content && data.timestamp) {
            setLastMessage(data as AgentMessage);
          }

          // Handle other message types (ack, error)
          if (data.type === "error") {
            console.error("WebSocket error message:", data.message);
          }
        } catch (parseError) {
          console.error("Failed to parse WebSocket message:", parseError);
        }
      };

      ws.onerror = () => {
        console.error("WebSocket error");
        setError("WebSocket connection error");
      };

      ws.onclose = () => {
        console.log("WebSocket closed");
        setIsConnected(false);
        wsRef.current = null;

        // Skip reconnection if intentionally closed (unmount or manual reconnect)
        if (intentionalCloseRef.current) {
          return;
        }

        // Attempt reconnection with exponential backoff
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++;
          const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current - 1);
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
  }, []);

  const sendMessage = useCallback((message: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn("WebSocket not connected, message not sent");
    }
  }, []);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    intentionalCloseRef.current = true;

    if (wsRef.current) {
      wsRef.current.close();
    }

    intentionalCloseRef.current = false;
    connect();
  }, [connect]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    isConnected,
    error,
    lastMessage,
    sendMessage,
    reconnect,
  };
}
