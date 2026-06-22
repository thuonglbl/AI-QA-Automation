/** Timezone helpers: the IANA option list for the admin form + message-time formatting. */

/** The browser's current IANA timezone (best-effort), used as the create-user default. */
export const BROWSER_TIMEZONE: string = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
})();

/** Full IANA timezone list for the admin create-user dropdown.
 *
 * `Intl.supportedValuesOf("timeZone")` returns every IANA zone the runtime knows, so the
 * dropdown stays valid against the backend's `zoneinfo` check without a hardcoded list.
 * Falls back to a minimal set on the rare runtime without it, always including UTC and the
 * browser's own zone so the default is selectable. */
export const TIMEZONE_OPTIONS: string[] = (() => {
  let zones: string[] = [];
  try {
    const supported = (
      Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    ).supportedValuesOf;
    if (supported) zones = supported("timeZone");
  } catch {
    zones = [];
  }
  const set = new Set<string>(zones.length ? zones : ["UTC"]);
  set.add("UTC");
  set.add(BROWSER_TIMEZONE);
  return Array.from(set).sort();
})();

function timeParts(timezone?: string): Intl.DateTimeFormatOptions {
  return {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...(timezone ? { timeZone: timezone } : {}),
  };
}

/** Format an ISO timestamp as hh:mm:ss in the given IANA timezone (browser zone if unset).
 *
 * Returns "" for a missing/invalid timestamp, and silently falls back to the browser zone
 * if `timezone` is not a valid IANA name. */
export function formatMessageTime(
  iso: string | undefined,
  timezone?: string,
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(undefined, timeParts(timezone)).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, timeParts()).format(date);
  }
}

/** Full localized date+time for a hover tooltip (browser zone fallback on invalid tz). */
export function formatMessageDateTime(
  iso: string | undefined,
  timezone?: string,
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const opts: Intl.DateTimeFormatOptions = {
    dateStyle: "medium",
    timeStyle: "medium",
    ...(timezone ? { timeZone: timezone } : {}),
  };
  try {
    return new Intl.DateTimeFormat(undefined, opts).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(date);
  }
}
