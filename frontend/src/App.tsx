import { useEffect, useState, useCallback } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePipelineState } from "@/hooks/usePipelineState";
import { useAuth } from "@/hooks/useAuth";
import { ProviderSelector } from "@/components/ProviderSelector";
import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
import { ProcessingIndicator } from "@/components/ProcessingIndicator";
import { LoginPage } from "@/components/auth/LoginPage";
import { ProjectPicker } from "@/components/projects/ProjectPicker";
import { AdminPanel } from "@/components/admin/AdminPanel";
import { useProject } from "@/hooks/useProject";
import type { ProviderOption, ModelAssignment } from "@/types/provider";
import type { AgentMessage } from "@/types/pipeline";
import { LogOut, FolderKanban } from "lucide-react";

// Default provider options - shown immediately without waiting for WebSocket
const DEFAULT_PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: "browser-use-cloud",
    name: "Browser Use Cloud",
    description: "Highest quality (78% benchmark) · Cloud servers · Personal API key required",
    qualityRank: 1,
    securityLevel: "cloud",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true, placeholder: "Enter your Browser Use API key..." }
    ]
  },
  {
    id: "claude",
    name: "Claude (Anthropic)",
    description: "Second highest quality (62%) · Enterprise license · API key or SSO login",
    qualityRank: 2,
    securityLevel: "enterprise",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true, placeholder: "Enter your Claude API key..." }
    ]
  },
  {
    id: "gemini-chatgpt",
    name: "Gemini / ChatGPT",
    description: "Good quality · Cloud · Personal API key from Google or OpenAI",
    qualityRank: 3,
    securityLevel: "cloud",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true, placeholder: "Enter your API key from Google or OpenAI..." }
    ]
  },
  {
    id: "on-premises",
    name: "On-Premises",
    description: "Highest security · All data stays on your infrastructure · Server URL + API key",
    qualityRank: 4,
    securityLevel: "highest",
    credentialFields: [
      { name: "server_url", label: "Server URL", type: "url", required: true, placeholder: "https://your-server.com" },
      { name: "api_key", label: "API Key", type: "password", required: true, placeholder: "Enter API key..." }
    ]
  }
];

interface SubmittedSelection {
  providerId: string;
  providerName: string;
  credentials: Record<string, string>;
}

interface AliceState {
  providerOptions: ProviderOption[] | null;
  onPremDefaults: { server_url: string; api_key: string } | undefined;
  modelAssignments: ModelAssignment[] | null;
  providerName: string;
  providerEndpoint: string;
  submittedSelection: SubmittedSelection | null;
}

function App() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const { selectedProject, selectedProjectId, isProjectReady, clearSelectedProject } = useProject();
  const { isConnected, error, lastMessage, sendMessage } = useWebSocket(selectedProjectId);
  const {
    status,
    currentStep,
    messages,
    isLoaded,
    updateFromMessage,
    addUserMessage,
  } = usePipelineState();

  const [aliceState, setAliceState] = useState<AliceState>({
    providerOptions: DEFAULT_PROVIDER_OPTIONS,
    onPremDefaults: undefined,
    modelAssignments: null,
    providerName: "",
    providerEndpoint: "",
    submittedSelection: null,
  });

  // Handle WebSocket messages for Alice-specific UI
  const handleAliceMessage = useCallback((message: AgentMessage) => {
    // Provider options from backend (only update if user hasn't submitted yet)
    if (message.metadata?.type === "provider_options" && !aliceState.submittedSelection) {
      setAliceState((prev) => ({
        ...prev,
        providerOptions: message.metadata?.options as ProviderOption[] || null,
        onPremDefaults: message.metadata?.onPremDefaults as { server_url: string; api_key: string } | undefined,
      }));
    }

    // Model assignments for review
    if (message.metadata?.model_assignments) {
      setAliceState((prev) => ({
        ...prev,
        modelAssignments: message.metadata?.model_assignments as ModelAssignment[],
        providerName: (message.metadata?.configuration as { provider?: { provider_name?: string } })?.provider?.provider_name || "",
        providerEndpoint: (message.metadata?.provider_endpoint as string) || "",
      }));
    }

    // Note: We don't clear modelAssignments on processing anymore
    // to keep the review visible during the entire conversation
  }, [aliceState.submittedSelection]);

  // Update pipeline state when new messages arrive
  useEffect(() => {
    if (lastMessage) {
      updateFromMessage(lastMessage);
      handleAliceMessage(lastMessage);
    }
  }, [lastMessage, updateFromMessage, handleAliceMessage]);

  useEffect(() => {
    if (!error) return;
    const normalizedError = error.toLowerCase();
    const isProjectAuthorizationFailure =
      normalizedError.includes("403") ||
      normalizedError.includes("404") ||
      normalizedError.includes("forbidden") ||
      normalizedError.includes("not found") ||
      normalizedError.includes("project");

    if (isProjectAuthorizationFailure) {
      clearSelectedProject("Your selected project is no longer available. Please choose another project.");
    }
  }, [clearSelectedProject, error]);

  // Auto-navigate to Bob when Alice step is completed
  useEffect(() => {
    // Only navigate after conversation is fully loaded
    if (!isLoaded || !selectedProjectId) return;

    if (currentStep === 1 && (status === 'completed' || status === 'done')) {
      const timer = setTimeout(() => {
        sendMessage({
          type: "navigate",
          step: 2,
          direction: "next",
          agentName: "Bob",
          sender: "user",
          content: "Navigate to Bob",
          messageType: "info",
          projectId: selectedProjectId,
          project_id: selectedProjectId,
        });
      }, 2000); // 2 second delay to let user see the completion

      return () => {
        clearTimeout(timer);
      };
    }
  }, [currentStep, status, sendMessage, isLoaded, selectedProjectId]);

  // Handle provider selection
  const handleProviderSelect = useCallback((providerId: string, credentials: Record<string, string>) => {
    if (!selectedProjectId) {
      clearSelectedProject("Select a project before starting the pipeline.");
      return;
    }

    // Find provider name for display
    const provider = aliceState.providerOptions?.find(p => p.id === providerId);
    const providerName = provider?.name || providerId;

    // Save submitted selection to display as read-only
    setAliceState((prev) => ({
      ...prev,
      submittedSelection: {
        providerId: providerId,
        providerName: providerName || providerId,
        credentials: { ...credentials },
      },
    }));


    // Send provider selection to backend via WebSocket
    sendMessage({
      type: "start",
      step: 1,
      projectId: selectedProjectId,
      project_id: selectedProjectId,
      inputData: {
        provider: providerId,
        credentials,
        projectId: selectedProjectId,
        project_id: selectedProjectId,
      },
    });
  }, [sendMessage, aliceState.providerOptions, selectedProjectId, clearSelectedProject]);

  // Handle approve/reject
  const handleApprove = useCallback(() => {
    if (!selectedProjectId) return;
    // Add user message showing approval action
    addUserMessage("✓ Approve", "success");
    sendMessage({
      type: "approve",
      step: 1,
      projectId: selectedProjectId,
      project_id: selectedProjectId,
    });
  }, [sendMessage, addUserMessage, selectedProjectId]);

  const handleReject = useCallback(() => {
    if (!selectedProjectId) return;
    // Add user message showing rejection action
    addUserMessage("✗ Reject - Change provider", "error");
    sendMessage({
      type: "reject",
      step: 1,
      feedback: "Change provider",
      projectId: selectedProjectId,
      project_id: selectedProjectId,
    });
    // Reset to show provider options again
    setAliceState((prev) => ({
      ...prev,
      modelAssignments: null,
    }));
  }, [sendMessage, addUserMessage, selectedProjectId]);

  // Check if we should show Alice-specific UI
  const isAliceStep = currentStep === 1;
  // Always show ProviderSelector on Alice step (as read-only after submission)
  const showProviderSelector = isAliceStep && aliceState.providerOptions;
  // Show model review if we have assignments - always visible once assigned
  const showModelReview = aliceState.modelAssignments;
  const isProcessing = status === "processing";

  // Show login page if not authenticated
  if (!isAuthenticated && !isLoading) {
    return <LoginPage />;
  }

  if (isAuthenticated && !isProjectReady) {
    return <ProjectPicker />;
  }

  // Agent display names and colors
  const agents = [
    { id: 1, name: "Alice", role: "Config", color: "#ec4899" },
    { id: 2, name: "Bob", role: "Requirements", color: "#3b82f6" },
    { id: 3, name: "Mary", role: "Testcases", color: "#22c55e" },
    { id: 4, name: "Sarah", role: "Scripts", color: "#8b5cf6" },
    { id: 5, name: "Jack", role: "Run", color: "#f97316" },
  ];
  const currentAgent = agents[currentStep - 1] ?? agents[0];
  const safeAgent = currentAgent ?? agents[0];

  return (
    <div className="h-screen flex flex-col bg-[#0f172a] overflow-hidden">
      {/* Top Navigation */}
      <nav className="fixed top-0 left-0 right-0 bg-white border-b border-[#e2e8f0] px-6 py-2.5 flex items-center gap-3 z-50 shadow-sm">
        <div className="text-[15px] font-bold text-[#0f172a] whitespace-nowrap">
          AI <span className="text-[#3b82f6]">QA Automation</span>
        </div>
        <div className="w-px h-6 bg-[#e2e8f0]" />
        <div className="flex gap-0.5 flex-wrap">
          {agents.map((agent) => (
            <span
              key={agent.id}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap select-none ${
                currentStep === agent.id
                  ? "bg-[#3b82f6] text-white"
                  : "bg-transparent text-[#64748b]"
              }`}
            >
              {agent.id}. {agent.name} — {agent.role}
            </span>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {selectedProject && (
            <div className="hidden items-center gap-1 rounded-full bg-[#eff6ff] px-3 py-1.5 text-xs font-semibold text-[#2563eb] md:flex">
              <FolderKanban className="h-3.5 w-3.5" />
              {selectedProject.name}
              <button
                id="change-project-button"
                type="button"
                onClick={() => clearSelectedProject()}
                className="ml-1 rounded-full px-1 text-[#1d4ed8] hover:bg-blue-100"
              >
                Change
              </button>
            </div>
          )}
          {user && (
            <span className="text-xs text-[#64748b] mr-2">
              {user.name}
            </span>
          )}
          <button
            onClick={() => logout()}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-[#e2e8f0] bg-white text-xs font-medium text-[#64748b] hover:bg-[#f8fafc] transition-all"
          >
            <LogOut className="w-3.5 h-3.5" />
            Logout
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <div className="pt-14 flex-1 flex flex-col">
        <div className="w-full bg-white flex-1 flex flex-col">
          {/* Topbar */}
          <div className="px-5 py-3.5 border-b border-[#e2e8f0] flex items-center gap-3 bg-white">
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0"
              style={{ backgroundColor: safeAgent!.color }}
            >
              {safeAgent!.name[0]}
            </div>
            <div className="flex-1">
              <h3 className="text-[15px] font-semibold text-[#0f172a] leading-tight">
                {safeAgent!.name} — {safeAgent!.role}
              </h3>
              <div className="text-xs text-[#64748b] mt-0.5">
                Step {currentStep} of 5{isProcessing && " · Testing connection..."}
              </div>
            </div>
            <div className="flex gap-1 items-center mr-3">
              {agents.map((agent, idx) => (
                <span
                  key={agent.id}
                  className={`w-2 h-2 rounded-full transition-colors ${
                    idx + 1 < currentStep
                      ? "bg-[#22c55e]"
                      : idx + 1 === currentStep
                      ? isProcessing
                        ? "bg-[#f59e0b] animate-pulse"
                        : "bg-[#3b82f6]"
                      : "bg-[#e2e8f0]"
                  }`}
                />
              ))}
            </div>
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold ${
                status === "start"
                  ? "bg-[#f1f5f9] text-[#64748b]"
                  : status === "processing"
                  ? "bg-[#fffbeb] text-[#d97706]"
                  : status === "review_request"
                  ? "bg-[#eff6ff] text-[#2563eb]"
                  : "bg-[#f0fdf4] text-[#16a34a]"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  status === "start"
                    ? "bg-[#94a3b8]"
                    : status === "processing"
                    ? "bg-[#f59e0b] animate-pulse"
                    : status === "review_request"
                    ? "bg-[#3b82f6]"
                    : "bg-[#22c55e]"
                }`}
              />
              {status === "start"
                ? "Start"
                : status === "processing"
                ? "Processing"
                : status === "review_request"
                ? "Review"
                : "Done"}
            </span>
          </div>

          {/* Error display */}
          {error && (
            <div className="mx-5 mt-4 p-3 rounded-lg bg-red-50 text-red-600 border border-red-200 text-sm">
              {error}
            </div>
          )}

          {/* Chat Content - Scrollable container */}
          <div className="flex-1 bg-[#f8fafc] overflow-y-auto" style={{ maxHeight: 'calc(100vh - 120px)' }}>
            <div className="p-5 flex flex-col gap-4 min-h-0">
              {/* Alice Provider Selector - Always at top on Alice step */}
              {showProviderSelector && (
                <ProviderSelector
                  options={aliceState.providerOptions}
                  onPremDefaults={aliceState.onPremDefaults}
                  onSelect={handleProviderSelect}
                  disabled={!isConnected || !!aliceState.submittedSelection || !selectedProjectId}
                  submittedSelection={aliceState.submittedSelection}
                />
              )}

              {/* Processing Indicator - hide when we have model assignments */}
              {isProcessing && isAliceStep && !aliceState.modelAssignments && (
                <ProcessingIndicator
                  message="Testing connection to AI provider..."
                  isActive={true}
                />
              )}

              {/* Model Assignment Review - Show BEFORE user action messages */}
              {showModelReview && (
                <ModelAssignmentReview
                  provider={aliceState.providerName}
                  endpoint={aliceState.providerEndpoint}
                  assignments={aliceState.modelAssignments}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  disabled={!isConnected}
                />
              )}

              {/* User Action Messages (Approve/Reject) - Show AFTER ModelAssignmentReview */}
              {[...messages]
                .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
                .filter((msg) => {
                  // Only show user action messages here
                  if (msg.sender !== 'user') return false;
                  const content = msg.content?.toLowerCase() || '';
                  // Only show approve/reject messages
                  return content.includes('approve') || content.includes('reject');
                })
                .map((msg) => (
                  <div
                    key={msg.id}
                    className="w-[40%] min-w-0 self-end"
                  >
                    <div className="text-[11px] font-semibold mb-1 text-[#64748b] text-right">
                      You
                    </div>
                    <div className="p-4 text-sm leading-relaxed bg-[#3b82f6] text-white rounded-2xl rounded-br-sm">
                      {msg.content}
                    </div>
                  </div>
                ))}

              {/* Other Message History - Filter out processing/thinking and user action messages */}
              {[...messages]
                .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
                .filter((msg) => {
                  // Skip user action messages (shown above)
                  if (msg.sender === 'user') {
                    const content = msg.content?.toLowerCase() || '';
                    if (content.includes('approve') || content.includes('reject')) return false;
                  }
                  // Skip processing/thinking messages that are transient
                  const content = msg.content?.toLowerCase() || '';
                  if (content === 'processing' || content === 'review_request') return false;
                  if (content.includes('testing connection') && !content.includes('success')) return false;
                  // Skip provider options messages (rendered via ProviderSelector component)
                  if (msg.metadata?.type === 'provider_options') return false;
                  // Skip model assignments messages (rendered via ModelAssignmentReview component)
                  if (msg.metadata?.model_assignments) return false;
                  // Skip user input details (shown via submittedSelection in ProviderSelector)
                  if (msg.sender === 'user' && content.startsWith('provider:')) return false;
                  // Keep "successfully connected" messages visible as regular messages
                  // Skip "done" status messages
                  if (content === 'done') return false;
                  // Keep "AI Provider Configuration complete" visible until navigation
                  // Skip navigation messages (handled by state update)
                  if (msg.metadata?.type === 'navigation') return false;
                  return true;
                })
                .map((msg) => (
                  <div
                    key={msg.id}
                    className={`w-[40%] min-w-0 ${msg.sender === 'user' ? 'self-end' : 'self-start'}`}
                  >
                    <div className={`text-[11px] font-semibold mb-1 ${msg.sender === 'user' ? 'text-[#64748b] text-right' : 'text-[#3b82f6]'}`}>
                      {msg.sender === 'user' ? 'You' : msg.agentName || msg.sender}
                    </div>
                    <div className={`p-4 text-sm leading-relaxed ${msg.sender === 'user' ? 'bg-[#3b82f6] text-white rounded-2xl rounded-br-sm' : 'bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a]'}`}>
                      {msg.content}
                    </div>
                  </div>
                ))}

              {/* Empty state - only show when no messages or UI components */}
              {messages.length === 0 && !showProviderSelector && !showModelReview && (
                <div className="flex-1 flex items-center justify-center text-[#94a3b8]">
                  <div className="text-center">
                    <p className="mb-2">Waiting for messages...</p>
                    <p className="text-xs">
                      Connect to WebSocket to start the AI QA pipeline
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Input Area - Hidden when showing provider selector */}
          {(!showProviderSelector && !showModelReview) && (
            <div className="px-5 py-3.5 border-t border-[#e2e8f0] bg-white">
              {isProcessing ? (
                <div className="text-center text-[#94a3b8] text-xs py-3">
                  Alice is verifying your connection...
                </div>
              ) : (
                <div className="text-center text-[#94a3b8] text-xs py-3">
                  Waiting for input...
                </div>
              )}
            </div>
          )}
          {user?.role === "admin" && <AdminPanel />}
        </div>
      </div>
    </div>
  );
}

export default App;
