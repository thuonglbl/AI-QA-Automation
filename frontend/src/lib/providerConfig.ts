import { apiFetch } from "./api";
import type { ProviderConfigResponse } from "@/types/provider";

export function getThreadProviderConfig(
  threadId: string,
): Promise<ProviderConfigResponse> {
  return apiFetch<ProviderConfigResponse>(`/threads/${threadId}/provider-config`);
}
