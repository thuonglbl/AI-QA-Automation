/** AI Provider types for Alice step */

/** Provider identifier */
export type ProviderId =
  | "browser-use-cloud"
  | "claude"
  | "gemini-chatgpt"
  | "on-premises";

/** Security level for provider */
export type SecurityLevel = "cloud" | "enterprise" | "highest";

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
  qualityRank: number;
  securityLevel: SecurityLevel;
  credentialFields: CredentialField[];
}

/** Provider credentials */
export interface ProviderCredentials {
  api_key?: string;
  server_url?: string;
}

/** Model assignment for review */
export interface ModelAssignment {
  agent: string;
  model: string;
  purpose: string;
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
  onPremDefaults?: {
    server_url: string;
    api_key: string;
  };
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
};

/** Security level labels */
export const SECURITY_LEVEL_LABELS: Record<SecurityLevel, string> = {
  cloud: "Cloud",
  enterprise: "Enterprise",
  highest: "Highest Security",
};

/** Quality rank labels */
export const QUALITY_RANK_LABELS: Record<number, string> = {
  1: "1st Choice",
  2: "2nd Choice",
  3: "3rd Choice",
  4: "4th Choice",
};
