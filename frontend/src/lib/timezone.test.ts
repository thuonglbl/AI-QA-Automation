import { describe, expect, it } from "vitest";

import {
  TIMEZONE_OPTIONS,
  formatMessageTime,
  formatMessageDateTime,
} from "./timezone";

describe("formatMessageTime", () => {
  const iso = "2026-06-20T14:30:45Z";

  it("formats hh:mm:ss in the given timezone", () => {
    expect(formatMessageTime(iso, "UTC")).toBe("14:30:45");
  });

  it("shifts into a non-UTC zone (Asia/Ho_Chi_Minh = UTC+7, no DST)", () => {
    expect(formatMessageTime(iso, "Asia/Ho_Chi_Minh")).toBe("21:30:45");
  });

  it("returns empty string for a missing or invalid timestamp", () => {
    expect(formatMessageTime(undefined, "UTC")).toBe("");
    expect(formatMessageTime("not-a-date", "UTC")).toBe("");
  });

  it("falls back to the browser zone for an invalid timezone instead of throwing", () => {
    expect(() => formatMessageTime(iso, "Not/AZone")).not.toThrow();
    expect(formatMessageTime(iso, "Not/AZone")).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe("formatMessageDateTime", () => {
  it("returns a non-empty localized date+time", () => {
    const out = formatMessageDateTime("2026-06-20T14:30:45Z", "UTC");
    expect(out).not.toBe("");
  });
});

describe("TIMEZONE_OPTIONS", () => {
  it("always includes UTC", () => {
    expect(TIMEZONE_OPTIONS).toContain("UTC");
  });
});
