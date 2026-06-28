import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppVersion } from "../AppVersion";

describe("AppVersion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the injected __APP_VERSION__ with a 'v' prefix", () => {
    vi.stubGlobal("__APP_VERSION__", "1.2.3");
    render(<AppVersion />);
    const el = screen.getByTitle("Frontend Version");
    expect(el).toHaveTextContent("v1.2.3");
  });

  it("renders 'dev' fallback without 'v' prefix", () => {
    vi.stubGlobal("__APP_VERSION__", "dev");
    render(<AppVersion />);
    const el = screen.getByTitle("Frontend Version");
    expect(el).toHaveTextContent("dev");
  });

  it("renders 'unknown' fallback when __APP_VERSION__ is empty string", () => {
    vi.stubGlobal("__APP_VERSION__", "");
    render(<AppVersion />);
    const el = screen.getByTitle("Frontend Version");
    expect(el).toHaveTextContent("unknown");
  });

  it("renders 'unknown' fallback when __APP_VERSION__ is undefined", () => {
    vi.stubGlobal("__APP_VERSION__", undefined);
    render(<AppVersion />);
    const el = screen.getByTitle("Frontend Version");
    expect(el).toHaveTextContent("unknown");
  });
});
