import { test as base, expect } from "@playwright/test";

import { ApiClient } from "../helpers/api";
import { mockJsonResponse, blockUnexpectedApiCalls } from "../helpers/network";
import { UserFactory } from "./factories/userFactory";

type AppFixtures = {
  apiClient: ApiClient;
  userFactory: UserFactory;
  mockJson: typeof mockJsonResponse;
  blockUnexpectedApiCalls: typeof blockUnexpectedApiCalls;
};

export const test = base.extend<AppFixtures>({
  apiClient: async ({ request }, use) => {
    await use(new ApiClient({ request }));
  },

  userFactory: async ({}, use) => {
    const factory = new UserFactory();

    try {
      await use(factory);
    } finally {
      await factory.cleanup();
    }
  },

  mockJson: async ({}, use) => {
    await use((url, body, opts) => mockJsonResponse(url, body, opts));
  },

  blockUnexpectedApiCalls: async ({}, use) => {
    await use((allowed) => blockUnexpectedApiCalls(allowed));
  },
});

export { expect };
