import React, { useRef, useEffect, useState, useCallback } from "react";
import type { AgentMessage } from "@/types/pipeline";
import { ChatMessage } from "./ChatMessage";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { ArrowDown } from "lucide-react";

export interface ChatAreaProps {
  messages: AgentMessage[];
  className?: string;
}

// Debounce hook for scroll events
function useDebounce<T extends (...args: Parameters<T>) => void>(
  callback: T,
  delay: number,
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  return useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => callback(...args), delay);
    },
    [callback, delay],
  ) as T;
}

export function ChatArea({ messages, className }: ChatAreaProps) {
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const [isScrolledUp, setIsScrolledUp] = useState(false);
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const previousMessageCount = useRef(messages.length);

  useEffect(() => {
    const currentLength = messages.length;
    const isNewMessage = currentLength > previousMessageCount.current;

    if (isNewMessage) {
      if (isScrolledUp) {
        setHasNewMessage(true);
      } else {
        scrollToBottom();
      }
    } else if (!isScrolledUp) {
      scrollToBottom();
    }

    previousMessageCount.current = currentLength;
  }, [messages, isScrolledUp]);

  const scrollToBottom = () => {
    if (scrollViewportRef.current) {
      scrollViewportRef.current.scrollTop =
        scrollViewportRef.current.scrollHeight;
      setHasNewMessage(false);
    }
  };

  // Debounced scroll handler for performance
  const handleScroll = useDebounce((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const scrollPosition = target.scrollTop + target.clientHeight;
    // Use Math.ceil for fractional pixels, 1px threshold for precision
    const isAtBottom = Math.ceil(target.scrollHeight - scrollPosition) <= 1;

    if (isAtBottom) {
      setIsScrolledUp(false);
      setHasNewMessage(false);
    } else {
      setIsScrolledUp(true);
    }
  }, 16); // ~60fps debounce

  return (
    <div className={cn("relative flex w-full flex-col", className)}>
      <ScrollArea
        className="flex-1 w-full"
        viewportRef={scrollViewportRef}
        onScroll={handleScroll}
      >
        <div role="list" className="flex flex-col p-4 w-full h-full pb-10">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
        </div>
      </ScrollArea>

      {hasNewMessage && isScrolledUp && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-blue-600 text-white rounded-full px-4 py-1.5 text-xs font-semibold shadow-md active:scale-95 transition-transform hover:bg-blue-700"
        >
          <ArrowDown className="w-3 h-3" />
          New message
        </button>
      )}
    </div>
  );
}
