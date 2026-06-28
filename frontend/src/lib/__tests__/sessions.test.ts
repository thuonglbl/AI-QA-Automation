import { afterEach, describe, expect, it, vi } from "vitest";
import { buildConfiguredHelper, importWithTokenUrl } from "@/lib/sessions";

const CMD_TEMPLATE = [
  "@echo off",
  "rem __AIQA_CONFIG__",
  'node "%TMPJS%" --out="%OUTFILE%"',
].join("\r\n");

const MJS_TEMPLATE = [
  'import { writeFileSync } from "node:fs";',
  "// __AIQA_CONFIG__",
  "main();",
].join("\n");

function mockTemplateFetch(body: string) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body, { status: 200, headers: { "content-type": "text/plain" } }),
  );
}

async function blobText(blob: Blob): Promise<string> {
  return blob.text();
}

describe("importWithTokenUrl", () => {
  it("builds an absolute, API-base-prefixed endpoint URL", () => {
    expect(importWithTokenUrl("p1")).toBe(
      `${location.origin}/api/projects/p1/sessions/import-with-token`,
    );
  });
});

describe("buildConfiguredHelper", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("injects the batch config block at the cmd marker", async () => {
    mockTemplateFetch(CMD_TEMPLATE);
    const blob = await buildConfiguredHelper("cmd", {
      uploadUrl: "https://host/api/projects/p1/sessions/import-with-token",
      token: "tok-123",
      domain: "app.example.com",
    });
    const text = await blobText(blob);
    expect(text).toContain(
      'set "AIQA_UPLOAD_URL=https://host/api/projects/p1/sessions/import-with-token"',
    );
    expect(text).toContain('set "AIQA_TOKEN=tok-123"');
    expect(text).toContain('set "AIQA_DOMAIN=app.example.com"');
    // The marker is replaced, not left behind.
    expect(text).not.toContain("rem __AIQA_CONFIG__");
  });

  it("injects the JS config block at the mjs marker", async () => {
    mockTemplateFetch(MJS_TEMPLATE);
    const blob = await buildConfiguredHelper("mjs", {
      uploadUrl: "https://host/api/projects/p1/sessions/import-with-token",
      token: "tok-123",
      domain: "app.example.com",
    });
    const text = await blobText(blob);
    expect(text).toContain(
      'process.env.AIQA_UPLOAD_URL = "https://host/api/projects/p1/sessions/import-with-token";',
    );
    expect(text).toContain('process.env.AIQA_TOKEN = "tok-123";');
    expect(text).toContain('process.env.AIQA_DOMAIN = "app.example.com";');
    expect(text).not.toContain("// __AIQA_CONFIG__");
  });

  it("escapes batch-special characters so a value cannot break out of the set line", async () => {
    mockTemplateFetch(CMD_TEMPLATE);
    const blob = await buildConfiguredHelper("cmd", {
      uploadUrl: "https://host/api?a=1&b=2",
      token: "100%done",
      domain: "app.example.com",
    });
    const text = await blobText(blob);
    expect(text).toContain('set "AIQA_UPLOAD_URL=https://host/api?a=1^&b=2"');
    expect(text).toContain('set "AIQA_TOKEN=100%%done"');
  });

  it("escapes JS-special characters in the mjs block", async () => {
    mockTemplateFetch(MJS_TEMPLATE);
    const blob = await buildConfiguredHelper("mjs", {
      uploadUrl: 'https://host/"weird"',
      token: "a\\b",
      domain: "app.example.com",
    });
    const text = await blobText(blob);
    expect(text).toContain('process.env.AIQA_UPLOAD_URL = "https://host/\\"weird\\"";');
    expect(text).toContain('process.env.AIQA_TOKEN = "a\\\\b";');
  });

  it("throws when the template cannot be fetched", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("nope", { status: 404 }),
    );
    await expect(
      buildConfiguredHelper("cmd", { uploadUrl: "u", token: "t", domain: "d" }),
    ).rejects.toThrow(/capture helper template/i);
  });
});
