import { apiFetch } from "./api";

export interface Thread {
  id: string;
  user_id: string;
  project_id: string | null;
  title?: string | null;
  is_archived?: boolean;
  created_at: string;
  updated_at: string;
}

export function createThread(
  userId: string,
  projectId?: string | null,
): Promise<Thread> {
  const body: { user_id: string; project_id?: string } = { user_id: userId };
  if (projectId) {
    body.project_id = projectId;
  }
  return apiFetch<Thread>("/threads", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ThreadUpdate {
  title?: string;
  is_archived?: boolean;
}

export function updateThread(
  threadId: string,
  update: ThreadUpdate,
): Promise<Thread> {
  return apiFetch<Thread>(`/threads/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}
