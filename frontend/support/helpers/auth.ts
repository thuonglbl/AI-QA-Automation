import type { BrowserContext } from "@playwright/test";

export type SessionCookieOptions = {
  name?: string;
  value: string;
  domain?: string;
  path?: string;
};

export async function seedSessionCookie(
  context: BrowserContext,
  {
    name = process.env.SESSION_COOKIE_NAME ?? "aiqa_session",
    value,
    domain = "localhost",
    path = "/",
  }: SessionCookieOptions,
): Promise<void> {
  if (!value) {
    throw new Error("Cannot seed an empty session cookie value.");
  }

  await context.addCookies([
    {
      name,
      value,
      domain,
      path,
      httpOnly: true,
      sameSite: "Lax",
      secure: false,
    },
  ]);
}
