/** AI Provider types for Alice step */

/** Provider identifier */
export type ProviderId =
  | "browser-use-cloud"
  | "claude"
  | "claude-sso"
  | "openai"
  | "gemini"
  | "on-premises";

/** How a provider collects credentials in the UI. */
export type AuthMethod = "api_key" | "sso";

/** Security level for provider */
export type SecurityLevel = "cloud" | "enterprise" | "highest" | "good";

/** Credential field type */
export type CredentialFieldType = "text" | "password" | "url";

/** Credential field definition */
export interface CredentialField {
  name: string;
  label: string;
  type: CredentialFieldType;
  required: boolean;
  placeholder?: string;
}

/** Provider option for selection UI */
export interface ProviderOption {
  id: ProviderId;
  name: string;
  description: string;
  qualityRank: number;
  securityLevel: SecurityLevel;
  /** "sso" renders a Login-SSO button; "api_key" (default) renders credential inputs. */
  authMethod?: AuthMethod;
  credentialFields: CredentialField[];
}

/** Provider credentials */
export interface ProviderCredentials {
  api_key?: string;
  server_url?: string;
}

/** Provider benchmark ranking hint (non-secret) surfaced in the review UI */
export interface ProviderBenchmark {
  accuracy_percent?: number;
  benchmark?: string;
  source_url?: string;
  note?: string;
}

/** Model assignment for review */
export interface ModelAssignment {
  agent: string;
  model: string;
  purpose: string;
  rationale: string;
}

/** Connection test status */
export type ConnectionTestStatus = "testing" | "success" | "failed";

/** Connection test message */
export interface ConnectionTestMessage {
  type: "connection_test";
  status: ConnectionTestStatus;
  message: string;
}

/** Provider options message from backend */
export interface ProviderOptionsMessage {
  type: "provider_options";
  options: ProviderOption[];
  on_prem_defaults?: {
    server_url?: string;
    api_key_configured: boolean;
  };
}

/** Per-agent entry in provider config response */
export interface AgentConfigEntry {
  agent: string;
  model: string | null;
  temperature: number;
  rationale: string;
}

/** Response from GET /api/threads/{thread_id}/provider-config */
export interface ProviderConfigResponse {
  configured: boolean;
  source: "thread" | "saved" | "none";
  provider: string | null;
  provider_name: string | null;
  endpoint: string | null;
  test_result: string | null;
  tested_at: string | null;
  agents: AgentConfigEntry[];
}

/** saved_config_prompt WebSocket metadata (Task 4) */
export interface SavedConfigPrompt {
  type: "saved_config_prompt";
  saved_config: {
    provider_name: string;
    endpoint: string;
    agents: AgentConfigEntry[];
  };
  options: ProviderOption[];
  enabled_providers: string[];
}

/** Thinking trace data from Alice */
export interface ThinkingTrace {
  connection_status?: "success" | "failed";
  available_models?: { id: string; name: string }[];
  unavailable_models?: { id: string; name: string; status: string }[];
  bootstrap_model?: string | null;
  bootstrap_rationale?: string | null;
  agent_needs?: Record<string, string>;
  assignments?: {
    agent: string;
    model: string;
    rationale: string;
    tier_source?: string;
    score_breakdown?: string;
  }[];
  benchmark?: ProviderBenchmark | null;
  chain_of_thought?: string[];
}

/** Thinking trace message */
export interface ThinkingTraceMessage {
  type: "thinking_trace";
  trace: ThinkingTrace;
}

/** Model assignment message from backend */
export interface ModelAssignmentMessage {
  type: "model_assignment";
  provider: string;
  assignments: ModelAssignment[];
  endpoint: string;
}

/** Provider configuration (from provider.json) */
export interface ProviderConfig {
  provider: ProviderId;
  provider_name: string;
  endpoint: string;
  credential_reference: string;
  tested_at: string;
  test_result: "success" | "failed";
}

/** Agent model configuration */
export interface AgentModelConfig {
  model: string;
  temperature: number;
  prompt_template: string;
  tools: string[];
}

/** Agents configuration (from agents.json) */
export interface AgentsConfig {
  version: string;
  updated_at: string;
  agents: Record<string, AgentModelConfig>;
}

/** Complete Alice configuration */
export interface AliceConfiguration {
  provider: ProviderConfig;
  agents: AgentsConfig;
}

/** Security level badge colors */
export const SECURITY_LEVEL_COLORS: Record<SecurityLevel, string> = {
  cloud: "bg-blue-100 text-blue-700",
  enterprise: "bg-purple-100 text-purple-700",
  highest: "bg-green-100 text-green-700",
  good: "bg-teal-100 text-teal-700",
};

/** Security level labels */
export const SECURITY_LEVEL_LABELS: Record<SecurityLevel, string> = {
  cloud: "Cloud",
  enterprise: "Enterprise",
  highest: "Highest Security",
  good: "Good Security",
};

/** Quality rank labels */
export const QUALITY_RANK_LABELS: Record<number, string> = {
  1: "1st Choice",
  2: "2nd Choice",
  3: "3rd Choice",
  4: "4th Choice",
  5: "5th Choice",
};
