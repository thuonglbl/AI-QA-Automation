import type { Page, Route } from "@playwright/test";

type JsonRouteOptions = {
  status?: number;
  headers?: Record<string, string>;
};

export async function mockJsonResponse(
  page: Page,
  url: string | RegExp,
  body: unknown,
  { status = 200, headers = {} }: JsonRouteOptions = {},
): Promise<void> {
  await page.route(url, async (route: Route) => {
    await route.fulfill({
      status,
      contentType: "application/json",
      headers,
      body: JSON.stringify(body),
    });
  });
}

export async function blockUnexpectedApiCalls(
  page: Page,
  allowed: Array<string | RegExp> = [],
): Promise<void> {
  await page.route(/\/api\//, async (route) => {
    const requestUrl = route.request().url();
    const isAllowed = allowed.some((pattern) =>
      typeof pattern === "string"
        ? requestUrl.includes(pattern)
        : pattern.test(requestUrl),
    );

    if (isAllowed) {
      await route.continue();
      return;
    }

    throw new Error(`Unexpected API request: ${requestUrl}`);
  });
}
