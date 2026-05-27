import { useEffect, useState, useCallback, Fragment } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePipelineState } from "@/hooks/usePipelineState";
import { useAuth } from "@/hooks/useAuth";
import { ProviderSelector } from "@/components/ProviderSelector";
import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
import { ProcessingIndicator } from "@/components/ProcessingIndicator";
import { LoginPage } from "@/components/auth/LoginPage";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { ThinkingBubble } from "@/components/ThinkingBubble";
import { SplitPanel } from "@/components/SplitPanel";
import { useProject } from "@/hooks/useProject";
import type { ProviderOption, ModelAssignment, ThinkingTrace } from "@/types/provider";
import type { AgentMessage } from "@/types/pipeline";
import { LogOut } from "lucide-react";

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
    description: "Highest security · All data stays on your infrastructure · Company API key",
    qualityRank: 4,
    securityLevel: "highest",
    credentialFields: [
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
  providerOptions: ProviderOption[];
  onPremDefaults: { server_url: string; api_key: string } | undefined;
  modelAssignments: ModelAssignment[] | null;
  providerName: string;
  providerEndpoint: string;
  submittedSelection: SubmittedSelection | null;
  thinkingTrace: ThinkingTrace | null;
}

interface BobState {
  mcpPat: string;
  isPaginating: boolean;
  isConfirmParent: boolean;
  suggestedPage: string;
  pageMetadata: any;
  extractedPages: Array<{
    page_id: string;
    page_title: string;
    source_url: string;
    raw_html: string;
    requirement_md: string;
  }> | null;
  submittedMcp?: boolean;
  thinkingTrace?: ThinkingTrace | null;
}

function App() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const {
    projects,
    selectedProject,
    selectedProjectId,
    isLoadingProjects,
    projectError,
    isProjectReady,
    selectProject,
    clearSelectedProject,
  } = useProject();

  const [autoSelectedProjectId, setAutoSelectedProjectId] = useState<string | null>(null);
  const [sessionSelectedProjectId, setSessionSelectedProjectId] = useState<string | null>(null);

  const confirmedProjectId = isProjectReady && sessionSelectedProjectId === selectedProjectId ? selectedProjectId : null;
  const { isConnected, error: wsError, messageQueue, clearMessageQueue, sendMessage } = useWebSocket(confirmedProjectId);
  const {
    status,
    currentStep,
    messages,
    isLoaded,
    updateFromMessage,
    addUserMessage,
  } = usePipelineState(selectedProjectId);

  const [aliceState, setAliceState] = useState<AliceState>({
    providerOptions: DEFAULT_PROVIDER_OPTIONS,
    onPremDefaults: undefined,
    modelAssignments: null,
    providerName: "",
    providerEndpoint: "",
    submittedSelection: null,
    thinkingTrace: null,
  });
  const isAliceStep = currentStep === 1;

  const [bobState, setBobState] = useState<BobState>({
    mcpPat: "",
    isPaginating: false,
    isConfirmParent: false,
    suggestedPage: "",
    pageMetadata: null,
    extractedPages: null,
    submittedMcp: false,
  });
  const isBobStep = currentStep === 2;

  const resetAliceConfiguration = useCallback(() => {
    setAliceState((prev) => ({ ...prev, submittedSelection: null, modelAssignments: null, thinkingTrace: null }));
  }, []);

  // Handle WebSocket messages for Alice-specific UI
  const handleAliceMessage = useCallback((message: AgentMessage) => {
    if (message.agentName && message.agentName !== "Alice") return;

    // Provider options from backend (only update if user hasn't submitted yet)
    if (message.metadata?.type === "provider_options" && !aliceState.submittedSelection) {
      setAliceState((prev) => ({
        ...prev,
        providerOptions: message.metadata?.options as ProviderOption[] || null,
        onPremDefaults: message.metadata?.onPremDefaults as { server_url: string; api_key: string } | undefined,
      }));
    }

    // Model assignments for review
    const resultData = (message.metadata?.result as any)?.data || message.metadata;
    if (resultData?.model_assignments) {
      setAliceState((prev) => ({
        ...prev,
        modelAssignments: resultData.model_assignments as ModelAssignment[],
        providerName: (resultData.configuration as { provider?: { provider_name?: string } })?.provider?.provider_name || "",
        providerEndpoint: (resultData.provider_endpoint as string) || "",
      }));
    }
    
    // Thinking Trace
    if (message.metadata?.type === "thinking_trace") {
      setAliceState((prev) => ({
        ...prev,
        thinkingTrace: message.metadata?.trace as ThinkingTrace,
      }));
    }

    // Note: We don't clear modelAssignments on processing anymore
    // to keep the review visible during the entire conversation
  }, [aliceState.submittedSelection]);

  // Handle WebSocket messages for Bob-specific UI
  const handleBobMessage = useCallback((message: AgentMessage, currentProjectUrl?: string | null) => {
    if (message.agentName && message.agentName !== "Bob") return;

    if (message.metadata?.is_confirm_parent) {
      setBobState((prev) => {
        let newSuggested = (message.metadata?.suggested_page as string) || "";
        if (newSuggested === "Requirements" || newSuggested === "Requirement" || newSuggested === "") {
          newSuggested = currentProjectUrl || newSuggested;
        }
        return {
          ...prev,
          isConfirmParent: true,
          suggestedPage: newSuggested,
        };
      });
    } else if (message.metadata?.is_review_ready) {
      setBobState((prev) => ({
        ...prev,
        isConfirmParent: false,
        isPaginating: true,
        extractedPages: (message.metadata?.pages as any) || [],
      }));
    }
    
    // Thinking Trace
    if (message.metadata?.type === "thinking_trace") {
      setBobState((prev) => ({
        ...prev,
        thinkingTrace: message.metadata?.trace as ThinkingTrace,
      }));
    }
  }, []);

  useEffect(() => {
    if (!isAliceStep || isLoadingProjects || projects.length !== 1) return;
    const [onlyProject] = projects;
    if (!onlyProject || autoSelectedProjectId === onlyProject.id) return;

    if (selectedProjectId && selectedProjectId !== onlyProject.id) return;

    if (!selectedProjectId) {
      selectProject(onlyProject.id);
    }
    setAutoSelectedProjectId(onlyProject.id);
    setSessionSelectedProjectId(onlyProject.id);
  }, [autoSelectedProjectId, isLoadingProjects, isAliceStep, projects, selectProject, selectedProjectId]);

  const handleProjectSelect = useCallback((projectId: string) => {
    const project = projects.find((candidate) => candidate.id === projectId);
    if (!project) return;

    resetAliceConfiguration();
    selectProject(project.id);
    setSessionSelectedProjectId(project.id);
  }, [projects, resetAliceConfiguration, selectProject]);


  useEffect(() => {
    if (messageQueue.length > 0) {
      messageQueue.forEach((msg) => {
        updateFromMessage(msg);
        handleAliceMessage(msg);
        handleBobMessage(msg, selectedProject?.confluence_base_url);
      });
      clearMessageQueue();
    }
  }, [messageQueue, updateFromMessage, handleAliceMessage, handleBobMessage, clearMessageQueue, selectedProject]);

  // Sync state from messages when history is loaded
  useEffect(() => {
    if (isLoaded && messages.length > 0) {
      messages.forEach(msg => {
        handleAliceMessage(msg);
        handleBobMessage(msg, selectedProject?.confluence_base_url);
      });
    }
  }, [isLoaded, handleAliceMessage, handleBobMessage, messages, selectedProject?.confluence_base_url]);

  useEffect(() => {
    if (!wsError) return;
    const normalizedError = wsError.toLowerCase();
    const isProjectAuthorizationFailure =
      normalizedError.includes("403") ||
      normalizedError.includes("404") ||
      normalizedError.includes("forbidden") ||
      normalizedError.includes("not found") ||
      normalizedError.includes("project");

    if (isProjectAuthorizationFailure) {
      clearSelectedProject("Your selected project is no longer available. Please choose another project.");
      resetAliceConfiguration();
      setAutoSelectedProjectId(null);
      setSessionSelectedProjectId(null);
    }
  }, [clearSelectedProject, wsError, resetAliceConfiguration]);

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

  // Handle Bob start
  const handleBobStart = useCallback(() => {
    if (!selectedProjectId) return;
    
    setBobState(prev => ({...prev, submittedMcp: true}));
    // Add user message
    addUserMessage("Start requirements extraction", "info", { type: "bob_start" });
    
    sendMessage({
      type: "start",
      step: 2,
      projectId: selectedProjectId,
      project_id: selectedProjectId,
      inputData: {
        mcp_pat: bobState.mcpPat,
        confluence_url: selectedProject?.confluence_base_url ?? "",
      },
    });
  }, [sendMessage, addUserMessage, selectedProjectId, bobState.mcpPat, selectedProject]);

  const handleApprove = useCallback((updatedAssignments?: Record<string, string>) => {
    if (!selectedProjectId) return;
    // Add user message showing approval action
    addUserMessage("✓ OK", "success");
    sendMessage({
      type: "approve",
      step: currentStep,
      projectId: selectedProjectId,
      project_id: selectedProjectId,
      data: {
        assignments: updatedAssignments
      }
    });
  }, [sendMessage, addUserMessage, selectedProjectId, currentStep]);

  const handleBobApproveParent = useCallback((suggestedPage: string) => {
    if (!selectedProjectId) return;
    sendMessage({
      type: "approve",
      step: 2,
      projectId: selectedProjectId,
      data: { confirmed_page_name: suggestedPage }
    });
  }, [selectedProjectId, sendMessage]);

  const handleBobApprove = useCallback((pageId: string, updatedMarkdown: string) => {
    if (!selectedProjectId) return;
    sendMessage({
      type: "approve",
      step: 2,
      projectId: selectedProjectId,
      data: { action: "approved", page_id: pageId, markdown: updatedMarkdown }
    });
  }, [selectedProjectId, sendMessage]);

  const handleBobSkip = useCallback((pageId: string) => {
    if (!selectedProjectId) return;
    sendMessage({
      type: "approve",
      step: 2,
      projectId: selectedProjectId,
      data: { action: "not_requirement", page_id: pageId }
    });
  }, [selectedProjectId, sendMessage]);

  // Check if we should show Alice-specific UI
  const hasConfirmedProject = Boolean(selectedProject && selectedProjectId && sessionSelectedProjectId === selectedProjectId);
  // Show ProviderSelector only after Alice has resolved project context.
  const showProviderSelector = isAliceStep && hasConfirmedProject && aliceState.providerOptions;
  // Show model review if we have assignments - always visible once assigned
  const showModelReview = aliceState.modelAssignments;
  const isProcessing = status === "processing";

  // Show login page if not authenticated
  if (!isAuthenticated && !isLoading) {
    return <LoginPage />;
  }

  if (isAuthenticated && user?.role?.toLowerCase() === "admin") {
    return <AdminDashboard />;
  }

  // Agent display names and colors
  const agents = [
    { id: 1, name: "Alice", role: "Config", color: "#ec4899", colorClass: "bg-[#ec4899]" },
    { id: 2, name: "Bob", role: "Requirements", color: "#3b82f6", colorClass: "bg-[#3b82f6]" },
    { id: 3, name: "Mary", role: "Testcases", color: "#22c55e", colorClass: "bg-[#22c55e]" },
    { id: 4, name: "Sarah", role: "Scripts", color: "#8b5cf6", colorClass: "bg-[#8b5cf6]" },
    { id: 5, name: "Jack", role: "Run", color: "#f97316", colorClass: "bg-[#f97316]" },
  ];
  const fallbackAgent = { id: 1, name: "Alice", role: "Config", color: "#ec4899", colorClass: "bg-[#ec4899]" };
  const safeAgent = agents[(currentStep ?? 1) - 1] ?? agents[0] ?? fallbackAgent;

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
              className={`w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0 ${safeAgent.colorClass}`}
            >
              {safeAgent.name[0]}
            </div>
            <div className="flex-1">
              <h3 className="text-[15px] font-semibold text-[#0f172a] leading-tight">
                {safeAgent.name} — {safeAgent.role}
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
          {wsError && (
            <div className="bg-[#fee2e2] text-[#ef4444] px-4 py-3 rounded text-sm mb-6 flex justify-between items-center shadow-sm border border-[#f87171]/20">
              {wsError}
            </div>
          )}

          {/* Chat Content - Scrollable container */}
          <div className="flex-1 bg-[#f8fafc] overflow-y-auto max-h-[calc(100vh-120px)]">
            <div className="p-5 flex flex-col gap-4 min-h-0">
              {/* Alice Project Resolution - keep visible as the first chat message. */}
              {(!hasConfirmedProject || projects.length > 1) && (
                <div className="w-[40%] min-w-[18rem] max-w-xl self-start">
                  <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Alice</div>
                  <div className="p-4 text-sm leading-relaxed bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm">
                    {isLoadingProjects ? (
                      <p>Loading your accessible projects...</p>
                    ) : projectError ? (
                      <p>{projectError}</p>
                    ) : projects.length === 0 ? (
                      <p>You do not have access to any project yet. Please contact an administrator to assign you to a project.</p>
                    ) : projects.length > 1 ? (
                      <div className="space-y-3">
                        <p>Please select one project to proceed</p>
                        <div className="flex flex-col gap-2">
                          {projects.map((project) => {
                            const isSelectedProject = sessionSelectedProjectId === project.id;

                            return (
                              <button
                                id={`alice-project-option-${project.id}`}
                                key={project.id}
                                type="button"
                                onClick={() => handleProjectSelect(project.id)}
                                className={`rounded-xl border px-4 py-2.5 text-left font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-[#3b82f6] ${
                                  isSelectedProject
                                    ? "border-[#3b82f6] bg-[#dbeafe] text-[#1d4ed8]"
                                    : "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8] hover:-translate-y-0.5 hover:border-[#60a5fa] hover:bg-[#dbeafe]"
                                }`}
                              >
                                {project.name}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}

              {selectedProject && projects.length === 1 && hasConfirmedProject && (
                <div className="w-[40%] min-w-[18rem] max-w-xl self-start">
                  <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Alice</div>
                  <div className="p-4 text-sm leading-relaxed bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm">
                    You have only one project called {selectedProject.name}. Auto proceed with this project.
                  </div>
                </div>
              )}

              {isAliceStep && selectedProject && hasConfirmedProject && projects.length > 1 && (
                <div className="w-[40%] min-w-0 self-end">
                  <div className="text-[11px] font-semibold mb-1 text-[#64748b] text-right">You</div>
                  <div className="p-4 text-sm leading-relaxed bg-[#3b82f6] text-white rounded-2xl rounded-br-sm">
                    {selectedProject.name}
                  </div>
                </div>
              )}

              {/* Alice Provider Selector - shown after project resolution */}
              {hasConfirmedProject && aliceState.providerOptions.length > 0 && (
                <ProviderSelector
                  options={aliceState.providerOptions}
                  onPremDefaults={aliceState.onPremDefaults}
                  onSelect={handleProviderSelect}
                  disabled={!isConnected || !!aliceState.submittedSelection || !selectedProjectId}
                  submittedSelection={aliceState.submittedSelection}
                />
              )}

              {/* Processing Indicator - hide when we have model assignments */}
              {isProcessing && !aliceState.modelAssignments && (
                <ProcessingIndicator
                  message="Testing connection to AI provider..."
                  isActive={true}
                />
              )}

              {/* Thinking Trace */}
              {aliceState.thinkingTrace && (
                <ThinkingBubble trace={aliceState.thinkingTrace} title="Alice's thought" />
              )}

              {/* Model Assignment Review - Show BEFORE user action messages */}
              {!!aliceState.modelAssignments && (
                <ModelAssignmentReview
                  provider={aliceState.providerName}
                  endpoint={aliceState.providerEndpoint}
                  assignments={aliceState.modelAssignments}
                  availableModels={aliceState.thinkingTrace?.available_models?.map(m => m.id)}
                  onApprove={handleApprove}
                  disabled={!isConnected}
                />
              )}


              {/* Unified Message History - Chronological Order */}
              {[...messages]
                .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
                .filter((msg) => {
                  // Skip processing/thinking messages that are transient
                  const content = msg.content?.toLowerCase() || '';
                  if (content === 'processing' || content === 'review_request') return false;
                  if (content.includes('testing connection') && !content.includes('success')) return false;
                  // Skip provider options messages (rendered via ProviderSelector component)
                  if (msg.metadata?.type === 'provider_options') return false;
                  // Skip thinking trace messages (rendered via ThinkingBubble component)
                  if (msg.metadata?.type === 'thinking_trace') return false;
                  // Skip model assignments messages (rendered via ModelAssignmentReview component)
                  if (msg.metadata?.model_assignments) return false;
                  // Skip project selection message because it is rendered inline to preserve chat flow:
                  // Alice asks for project -> user chooses project -> Alice asks for provider.
                  if (
                    msg.sender === 'user' &&
                    selectedProject &&
                    hasConfirmedProject &&
                    content === selectedProject.name.toLowerCase()
                  ) return false;
                  // Keep "successfully connected" messages visible as regular messages
                  // Skip "done", "error", "start" status messages
                  if (content === 'done' || content === 'error' || content === 'start') return false;
                  // Keep "AI Provider Configuration complete" visible until navigation
                  // Skip navigation messages (handled by state update)
                  if (msg.metadata?.type === 'navigation') return false;
                  // Skip redundant confirm_parent messages (old text and new text)
                  if (msg.metadata?.is_confirm_parent || content.includes("contains all requirements, is it correct?")) return false;
                  // DO NOT skip bob_start message anymore, we will render MCP input right before it
                  return true;
                })
                .map((msg) => {
                  if (msg.metadata?.type === 'bob_start') {
                    return (
                      <Fragment key={msg.id}>
                        {/* Bob MCP Input rendered right before the user start message */}
                        {isBobStep && (
                          <div className="w-[85%] max-w-4xl self-start mb-4">
                            <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Bob</div>
                            <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                              <p className="text-sm font-medium">Please enter your MCP key to continue</p>
                              <div className="flex gap-3">
                                <input
                                  type="password"
                                  placeholder="Enter MCP API Key..."
                                  value={bobState.mcpPat}
                                  onChange={(e) => setBobState(prev => ({...prev, mcpPat: e.target.value}))}
                                  disabled={bobState.submittedMcp}
                                  className="flex-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
                                />
                                {!bobState.submittedMcp && (
                                  <button
                                    onClick={handleBobStart}
                                    disabled={!bobState.mcpPat || !isConnected}
                                    className="bg-[#3b82f6] text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                  >
                                    Start
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                        {/* The bob_start message itself */}
                        <div className="w-[40%] min-w-0 self-end">
                          <div className="text-[11px] font-semibold mb-1 text-[#64748b] text-right">You</div>
                          <div className="p-4 text-sm leading-relaxed bg-[#3b82f6] text-white rounded-2xl rounded-br-sm">
                            {msg.content}
                          </div>
                        </div>
                      </Fragment>
                    );
                  }

                  return (
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
                )})}
                
              {/* If Bob MCP Input hasn't been rendered yet because bob_start doesn't exist */}
              {!messages.some(m => m.metadata?.type === 'bob_start') && isBobStep && (status === "start" || bobState.submittedMcp) && (
                <div className="w-[85%] max-w-4xl self-start mt-4">
                  <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Bob</div>
                  <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                    <p className="text-sm font-medium">Please enter your MCP key to continue</p>
                    <div className="flex gap-3">
                      <input
                        type="password"
                        placeholder="Enter MCP API Key..."
                        value={bobState.mcpPat}
                        onChange={(e) => setBobState(prev => ({...prev, mcpPat: e.target.value}))}
                        disabled={bobState.submittedMcp}
                        className="flex-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
                      />
                      {!bobState.submittedMcp && (
                        <button
                          onClick={handleBobStart}
                          disabled={!bobState.mcpPat || !isConnected}
                          className="bg-[#3b82f6] text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          Start
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
              
              {/* Bob Thinking Trace */}
              {isBobStep && (bobState as any).thinkingTrace && (
                <ThinkingBubble trace={(bobState as any).thinkingTrace} title="Bob's thought" />
              )}
              
              {/* Bob Parent Page Confirmation */}
              {isBobStep && status === "review_request" && bobState.isConfirmParent && (
                <div className="w-[85%] max-w-4xl self-start">
                  <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Bob</div>
                  <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                    <p className="text-sm font-medium text-gray-700 leading-relaxed">
                      I found the below link contains all requirements, is it correct? If not, please input the correct one.
                    </p>
                    <div className="flex gap-3">
                      <input
                        type="text"
                        placeholder="Enter the correct page URL..."
                        value={bobState.suggestedPage}
                        onChange={(e) => setBobState(prev => ({...prev, suggestedPage: e.target.value}))}
                        className="flex-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent"
                      />
                      <button
                        onClick={() => handleBobApproveParent(bobState.suggestedPage)}
                        disabled={!bobState.suggestedPage || !isConnected}
                        className="bg-[#3b82f6] text-white px-8 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        OK
                      </button>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Bob Requirement Review */}
              {isBobStep && status === "review_request" && bobState.isPaginating && bobState.extractedPages && (
                <div className="w-[85%] max-w-5xl self-start">
                  <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">Bob</div>
                  <SplitPanel
                    pages={bobState.extractedPages}
                    currentIndex={0}
                    totalPages={bobState.extractedPages.length}
                    onApprove={handleBobApprove}
                    onSkip={handleBobSkip}
                    disabled={false}
                  />
                </div>
              )}

              {/* Empty state intentionally hidden to avoid exposing technical waiting states. */}
            </div>
          </div>

          {/* Input Area - Hidden until an actionable user step is available. */}
          {isProcessing && !showProviderSelector && !showModelReview && (
            <div className="px-5 py-3.5 border-t border-[#e2e8f0] bg-white">
              <div className="text-center text-[#94a3b8] text-xs py-3">
                Alice is verifying your connection...
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
