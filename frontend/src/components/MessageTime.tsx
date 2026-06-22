import { useContext, useState } from "react";

import { AuthContext } from "@/contexts/AuthContext";
import { formatMessageTime, formatMessageDateTime } from "@/lib/timezone";

/** Muted hh:mm:ss shown next to a message's sender name, in the logged-in user's
 * timezone (set by an admin at user creation; browser zone as fallback).
 *
 * `timestamp` is the message's server time when available. When it is missing/invalid
 * AND `fallbackToNow` is set, the component shows a client time frozen at first mount
 * instead of rendering nothing — so form/panel bubbles whose backing timestamp can't be
 * resolved (e.g. a reloaded carrier whose metadata didn't round-trip, or a marker filtered
 * out of the chat loop) still show a stable time. Without `fallbackToNow` it renders
 * nothing on a missing/invalid timestamp, so it stays safe to drop into any header.
 *
 * Reads the auth context directly (not via useAuth, which throws without a provider) so
 * it stays render-safe in isolated component tests — falling back to the browser zone. */
export function MessageTime({
  timestamp,
  fallbackToNow = false,
}: {
  timestamp?: string;
  fallbackToNow?: boolean;
}) {
  const timezone = useContext(AuthContext)?.user?.timezone;
  // Frozen at first mount so a fallback time doesn't tick on re-render. Declared
  // unconditionally to keep hook order stable; only consulted when there is no real time.
  const [mountIso] = useState(() => new Date().toISOString());
  const realTime = formatMessageTime(timestamp, timezone);
  const effectiveIso = realTime ? timestamp : fallbackToNow ? mountIso : undefined;
  const time = realTime || formatMessageTime(effectiveIso, timezone);
  if (!time) return null;
  return (
    <span
      className="ml-1.5 font-normal text-[#94a3b8]"
      title={formatMessageDateTime(effectiveIso, timezone)}
    >
      {time}
    </span>
  );
}

/** Like {@link MessageTime} but always shows a client time frozen at first mount — for
 * transient UI bubbles that have no server-backed message at all (e.g. the "loading
 * projects" / "enter MCP key" prompts). Thin wrapper over `MessageTime fallbackToNow`. */
export function NowMessageTime() {
  return <MessageTime fallbackToNow />;
}
