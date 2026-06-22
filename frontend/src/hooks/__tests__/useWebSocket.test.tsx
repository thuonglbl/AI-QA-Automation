import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "../useWebSocket";

/** Minimal stand-in for the browser WebSocket the hook constructs from
 * globalThis.WebSocket. It captures every instance so the test can drive
 * onopen/onmessage directly, and exposes open()/receive() test helpers. */
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  send = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  /** Simulate the socket opening. */
  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  /** Simulate a server frame (serialized exactly as the backend would). */
  receive(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

function lastSocket(): MockWebSocket {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  if (!ws) throw new Error("no MockWebSocket instance was created");
  return ws;
}

describe("useWebSocket message gate", () => {
  let originalWebSocket: typeof globalThis.WebSocket;

  beforeEach(() => {
    originalWebSocket = globalThis.WebSocket;
    MockWebSocket.instances = [];
    // @ts-expect-error — swap in the test stub for the real constructor.
    globalThis.WebSocket = MockWebSocket;
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
  });

  function mountConnected() {
    const hook = renderHook(() =>
      useWebSocket({ projectId: "p1", threadId: "t1" }),
    );
    const ws = lastSocket();
    act(() => ws.open());
    return { ...hook, ws };
  }

  it("queues a pure-metadata carrier sent with empty content", () => {
    const { result, ws } = mountConnected();

    // Alice's provider_options panel: content="" but a metadata.type is present.
    act(() =>
      ws.receive({
        sender: "agent",
        agentName: "Alice",
        content: "",
        timestamp: "2026-04-16T10:00:00Z",
        messageType: "info",
        metadata: { type: "provider_options" },
      }),
    );

    expect(result.current.messageQueue).toHaveLength(1);
    const queued = result.current.messageQueue[0];
    expect(queued?.metadata?.type).toBe("provider_options");
    expect(queued?.timestamp).toBe("2026-04-16T10:00:00Z");
  });

  it("still drops a frame with neither content nor metadata.type", () => {
    const { result, ws } = mountConnected();

    act(() =>
      ws.receive({
        sender: "agent",
        content: "",
        timestamp: "2026-04-16T10:00:00Z",
        messageType: "info",
      }),
    );

    expect(result.current.messageQueue).toHaveLength(0);
  });

  it("queues a normal non-empty-content message (unchanged behavior)", () => {
    const { result, ws } = mountConnected();

    act(() =>
      ws.receive({
        sender: "agent",
        agentName: "Bob",
        content: "Extraction complete",
        timestamp: "2026-04-16T10:01:00Z",
        messageType: "text",
      }),
    );

    expect(result.current.messageQueue).toHaveLength(1);
    expect(result.current.messageQueue[0]?.content).toBe("Extraction complete");
  });
});
