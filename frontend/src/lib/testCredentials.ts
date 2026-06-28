/** Typed client for the test-credentials API. */
import { apiFetch } from "@/lib/api";

export interface TestAccountCredentialResponse {
  id: string;
  environment: string;
  role: string;
  username: string;
  created_at: string;
  updated_at: string;
}

export interface TestAccountCredentialCreate {
  environment: string;
  role: string;
  username: string;
  password: string;
  totp_secret?: string | null;
}

export function listTestCredentials(projectId: string): Promise<TestAccountCredentialResponse[]> {
  return apiFetch<TestAccountCredentialResponse[]>(`/projects/${projectId}/test-credentials`);
}

export function upsertTestCredential(
  projectId: string,
  payload: TestAccountCredentialCreate,
): Promise<TestAccountCredentialResponse> {
  return apiFetch<TestAccountCredentialResponse>(`/projects/${projectId}/test-credentials`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteTestCredential(projectId: string, credentialId: string): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/test-credentials/${credentialId}`, {
    method: "DELETE",
  });
}

/** Attempt a real browser login using the user's saved test credentials for (env, role). */
export function testLogin(
  projectId: string,
  environment: string,
  role: string,
): Promise<{ success: boolean; error?: string }> {
  return apiFetch<{ success: boolean; error?: string }>(
    `/projects/${projectId}/test-credentials/test-login`,
    {
      method: "POST",
      body: JSON.stringify({ environment, role }),
    },
  );
}
