import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 7.6 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}

type RegisteredUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
};

type LoginResult = {
  access_token: string;
  user: RegisteredUser;
};

type AdminProject = {
  id: string;
  name: string;
  description: string | null;
};

type Thread = {
  id: string;
  user_id: string;
  project_id: string | null;
};

type AgentRun = {
  id: string;
  thread_id: string;
  status: string;
};

async function registerStandardUser(
  request: APIRequestContext,
  user: { email: string; displayName: string; password: string },
): Promise<RegisteredUser> {
  return createStandardUser(request, user);
}

async function login(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<LoginResult> {
  const response = await request.post(`${apiBaseUrl}/auth/login`, {
    data: { email, password },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<LoginResult>;
}

async function createAdminProject(
  request: APIRequestContext,
  token: string,
  name: string,
): Promise<AdminProject> {
  const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      description: `${name} description`,
      confluence_base_url: `https://confluence.example.test/${encodeURIComponent(name)}`,
      enabled_providers: ["on-premises"],
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AdminProject>;
}

async function assignMembership(
  request: APIRequestContext,
  token: string,
  projectId: string,
  userId: string,
): Promise<void> {
  const response = await request.post(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: userId, role: "member" },
    },
  );
  expect(response.ok()).toBeTruthy();
}

async function removeMembership(
  request: APIRequestContext,
  token: string,
  projectId: string,
  userId: string,
): Promise<void> {
  const response = await request.delete(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships/${userId}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(response.status()).toBe(204);
}

async function createThread(
  request: APIRequestContext,
  token: string,
  userId: string,
  projectId?: string,
): Promise<Thread> {
  const data: { user_id: string; project_id?: string } = { user_id: userId };
  if (projectId) {
    data.project_id = projectId;
  }
  const response = await request.post(`${apiBaseUrl}/api/threads`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<Thread>;
}

async function createRun(
  request: APIRequestContext,
  token: string,
  threadId: string,
  status: string,
): Promise<AgentRun> {
  const response = await request.post(
    `${apiBaseUrl}/api/threads/${threadId}/runs`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { status },
    },
  );
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AgentRun>;
}

// The backend auth middleware resolves the session COOKIE before the
// Authorization: Bearer header (see api/auth/middleware.py). Playwright's
// `request` fixture shares a single cookie jar per test, so logging in as the
// standard user would otherwise overwrite the admin's cookie and silently
// downgrade subsequent admin-token calls to the standard user (403). Each
// identity therefore gets its own isolated APIRequestContext / cookie jar.

test.describe("Story 7.6 Membership Removal Access Enforcement", () => {
  let createdUserIds: string[] = [];
  let createdProjectIds: string[] = [];

  test.afterEach(async ({ request }) => {
    if (createdUserIds.length === 0 && createdProjectIds.length === 0) return;
    try {
      const adminToken = await getAdminToken();
      for (const projectId of createdProjectIds) {
        await request.delete(`${apiBaseUrl}/api/admin/projects/${projectId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
      for (const userId of createdUserIds) {
        await request.delete(`${apiBaseUrl}/api/admin/users/${userId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
    } catch (e) {
      console.error(`Cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      createdUserIds = [];
      createdProjectIds = [];
    }
  });

  test("[P0] hides threads of a removed project but keeps unbound and still-member threads (AC1)", async ({
    request,
    playwright,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-7-6-list-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.6 List User",
      password: "list-secret-7-6",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const removedProject = await createAdminProject(
      request,
      adminToken,
      `S7.6 Removed ${Date.now()}`,
    );
    createdProjectIds.push(removedProject.id);
    const keptProject = await createAdminProject(
      request,
      adminToken,
      `S7.6 Kept ${Date.now()}`,
    );
    createdProjectIds.push(keptProject.id);

    await assignMembership(request, adminToken, removedProject.id, registeredUser.id);
    await assignMembership(request, adminToken, keptProject.id, registeredUser.id);

    // Isolated cookie jar for the standard user (see note above).
    const userContext = await playwright.request.newContext();
    try {
      const userLogin = await login(userContext, user.email, user.password);
      const userToken = userLogin.access_token;

      const removedThread = await createThread(
        userContext,
        userToken,
        registeredUser.id,
        removedProject.id,
      );
      const keptThread = await createThread(
        userContext,
        userToken,
        registeredUser.id,
        keptProject.id,
      );
      const unboundThread = await createThread(
        userContext,
        userToken,
        registeredUser.id,
      );

      // Admin revokes the user's membership on the first project only. This uses
      // the admin `request` jar, whose cookie is still the admin's.
      await removeMembership(request, adminToken, removedProject.id, registeredUser.id);

      const listResponse = await userContext.get(`${apiBaseUrl}/api/threads`, {
        headers: { Authorization: `Bearer ${userToken}` },
      });
      expect(listResponse.ok()).toBeTruthy();
      const threads = (await listResponse.json()) as Thread[];
      const visibleIds = threads.map((thread) => thread.id);

      expect(visibleIds).not.toContain(removedThread.id);
      expect(visibleIds).toContain(keptThread.id);
      expect(visibleIds).toContain(unboundThread.id);
    } finally {
      await userContext.dispose();
    }
  });

  test("[P0] denies every project-scoped thread endpoint with a generic 404 and no detail leak (AC2)", async ({
    request,
    playwright,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-7-6-deny-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.6 Deny User",
      password: "deny-secret-7-6",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const removedProject = await createAdminProject(
      request,
      adminToken,
      `S7.6 Deny Removed ${Date.now()}`,
    );
    createdProjectIds.push(removedProject.id);
    const keptProject = await createAdminProject(
      request,
      adminToken,
      `S7.6 Deny Kept ${Date.now()}`,
    );
    createdProjectIds.push(keptProject.id);

    await assignMembership(request, adminToken, removedProject.id, registeredUser.id);
    await assignMembership(request, adminToken, keptProject.id, registeredUser.id);

    // Isolated cookie jar for the standard user (see note above).
    const userContext = await playwright.request.newContext();
    try {
      const userLogin = await login(userContext, user.email, user.password);
      const userToken = userLogin.access_token;
      const authHeaders = { Authorization: `Bearer ${userToken}` };

      const boundThread = await createThread(
        userContext,
        userToken,
        registeredUser.id,
        removedProject.id,
      );
      const keptThread = await createThread(
        userContext,
        userToken,
        registeredUser.id,
        keptProject.id,
      );
      // Create a run while still a member so the PATCH endpoint has a real run id.
      const run = await createRun(userContext, userToken, boundThread.id, "running");

      // Membership revoked (admin jar): every project-scoped endpoint on
      // boundThread must now return a generic 404 with no thread/project/
      // artifact/agent-run detail.
      await removeMembership(request, adminToken, removedProject.id, registeredUser.id);

      const validConversation = {
        conversation: {
          messages: [],
          current_step: 1,
          status: "start",
          current_agent: "Alice",
          updated_at: new Date().toISOString(),
        },
      };

      const deniedRequests: Array<{
        label: string;
        send: () => Promise<import("@playwright/test").APIResponse>;
      }> = [
        {
          label: "GET /threads/{id}",
          send: () =>
            userContext.get(`${apiBaseUrl}/api/threads/${boundThread.id}`, {
              headers: authHeaders,
            }),
        },
        {
          label: "GET /threads/{id}/conversation",
          send: () =>
            userContext.get(
              `${apiBaseUrl}/api/threads/${boundThread.id}/conversation`,
              { headers: authHeaders },
            ),
        },
        {
          label: "POST /threads/{id}/conversation",
          send: () =>
            userContext.post(
              `${apiBaseUrl}/api/threads/${boundThread.id}/conversation`,
              { headers: authHeaders, data: validConversation },
            ),
        },
        {
          label: "GET /threads/{id}/messages",
          send: () =>
            userContext.get(
              `${apiBaseUrl}/api/threads/${boundThread.id}/messages`,
              { headers: authHeaders },
            ),
        },
        {
          label: "POST /threads/{id}/messages",
          send: () =>
            userContext.post(
              `${apiBaseUrl}/api/threads/${boundThread.id}/messages`,
              {
                headers: authHeaders,
                data: { sender: "user", content: "should not be accepted" },
              },
            ),
        },
        {
          label: "POST /threads/{id}/runs",
          send: () =>
            userContext.post(`${apiBaseUrl}/api/threads/${boundThread.id}/runs`, {
              headers: authHeaders,
              data: { status: "running" },
            }),
        },
        {
          label: "PATCH /threads/{id}/runs/{run_id}",
          send: () =>
            userContext.patch(
              `${apiBaseUrl}/api/threads/${boundThread.id}/runs/${run.id}`,
              {
                headers: authHeaders,
                data: { status: "completed" },
              },
            ),
        },
      ];

      const leakNeedles = [
        removedProject.name,
        "confluence",
        "conversation_data",
        "agent_runs",
        "password",
      ];

      for (const denied of deniedRequests) {
        const response = await denied.send();
        expect(response.status(), `${denied.label} should be denied`).toBe(404);
        const body = await response.json();
        // Generic, detail-free denial mirroring require_project_member_or_admin.
        expect(body.detail, `${denied.label} detail`).toBe("Resource not found");
        const serialized = JSON.stringify(body);
        for (const needle of leakNeedles) {
          expect(
            serialized,
            `${denied.label} must not leak "${needle}"`,
          ).not.toContain(needle);
        }
      }

      // Control: the owner is still a member of keptProject, so its bound thread
      // remains fully accessible — proving the gate is per-project, not global.
      const keptResponse = await userContext.get(
        `${apiBaseUrl}/api/threads/${keptThread.id}`,
        { headers: authHeaders },
      );
      expect(keptResponse.ok()).toBeTruthy();
      const keptBody = (await keptResponse.json()) as Thread;
      expect(keptBody.id).toBe(keptThread.id);
      expect(keptBody.project_id).toBe(keptProject.id);
    } finally {
      await userContext.dispose();
    }
  });
});
