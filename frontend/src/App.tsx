import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePipelineState } from "@/hooks/usePipelineState";
import { useAuth } from "@/hooks/useAuth";
import { createThread, type Thread } from "@/lib/threads";
import { apiFetch } from "@/lib/api";
import { getThreadProviderConfig } from "@/lib/providerConfig";
import { ProviderSelector } from "@/components/ProviderSelector";
import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
import { ProcessingIndicator } from "@/components/ProcessingIndicator";
import { ProviderConfigPanel } from "@/components/ProviderConfigPanel";
import { LoginPage } from "@/components/auth/LoginPage";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { ThinkingBubble } from "@/components/ThinkingBubble";
import { SplitPanel } from "@/components/SplitPanel";
import { ProjectSidebar } from "@/components/conversations/ProjectSidebar";
import { ArtifactNotice, type ArtifactNoticeType } from "@/components/artifacts/ArtifactNotice";
import { ArtifactPreview } from "@/components/artifacts/ArtifactPreview";
import type { Artifact } from "@/components/conversations/ProjectSidebar";
import { useProject } from "@/hooks/useProject";
import type {
  ProviderOption,
  ProviderId,
  SecurityLevel,
  CredentialField,
  ModelAssignment,
  ThinkingTrace,
  ProviderConfigResponse,
  SavedConfigPrompt,
} from "@/types/provider";
import type { AgentMessage } from "@/types/pipeline";
import { LogOut, PanelLeft } from "lucide-react";

// Default provider options - shown immediately without waiting for WebSocket
const DEFAULT_PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: "browser-use-cloud",
    name: "Browser Use Cloud",
    description: "Cloud · Personal API key",
    qualityRank: 1,
    securityLevel: "cloud",
    credentialFields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
        placeholder: "Enter your Browser Use API key...",
      },
    ],
  },
  {
    id: "claude",
    name: "Anthropic / Claude",
    description: "Cloud · Enterprise API key or SSO",
    qualityRank: 2,
    securityLevel: "enterprise",
    credentialFields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
        placeholder: "Enter your Claude API key...",
      },
    ],
  },
  {
    id: "gemini",
    name: "Google / Gemini",
    description: "Cloud · Personal API key",
    qualityRank: 3,
    securityLevel: "good",
    credentialFields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
        placeholder: "Enter your Google Gemini API key...",
      },
    ],
  },
  {
    id: "openai",
    name: "OpenAI / ChatGPT",
    description: "Cloud · Personal API key",
    qualityRank: 4,
    securityLevel: "good",
    credentialFields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
        placeholder: "Enter your OpenAI API key...",
      },
    ],
  },
  {
    id: "on-premises",
    name: "On-Premises",
    description: "Internal infrastructure · Company API key",
    qualityRank: 5,
    securityLevel: "highest",
    credentialFields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
        placeholder: "Enter API key...",
      },
    ],
  },
];

/**
 * Normalize a provider option coming from the backend WebSocket into the UI
 * model. The backend emits snake_case keys (`quality_rank`, `security_level`,
 * `credential_fields`); the UI model is camelCase. Without this mapping the
 * cast-only ingestion left `qualityRank`/`credentialFields` undefined, so the
 * selector rendered no icons/labels and — critically — no credential inputs,
 * making it impossible to enter an API key once backend options replaced the
 * camelCase defaults. Tolerant of either casing.
 */
const VALID_PROVIDER_IDS = new Set<string>([
  "browser-use-cloud",
  "claude",
  "openai",
  "gemini",
  "on-premises",
]);

function normalizeProviderOption(raw: unknown): ProviderOption {
  const o = (raw ?? {}) as Record<string, unknown>;
  const credentialFields =
    (o.credentialFields as CredentialField[] | undefined) ??
    (o.credential_fields as CredentialField[] | undefined) ??
    [];
  const rawId = o.id as string;
  return {
    id: VALID_PROVIDER_IDS.has(rawId) ? (rawId as ProviderId) : "on-premises",
    name: o.name as string,
    description: (o.description as string) ?? "",
    qualityRank: (o.qualityRank as number) ?? (o.quality_rank as number) ?? 0,
    securityLevel:
      (o.securityLevel as SecurityLevel) ??
      (o.security_level as SecurityLevel) ??
      "cloud",
    credentialFields,
  };
}

interface SubmittedSelection {
  providerId: string;
  providerName: string;
  credentials: Record<string, string>;
}

interface AliceState {
  providerOptions: ProviderOption[];
  onPremDefaults: { server_url?: string; api_key_configured: boolean } | undefined;
  modelAssignments: ModelAssignment[] | null;
  providerName: string;
  providerEndpoint: string;
  submittedSelection: SubmittedSelection | null;
  thinkingTrace: ThinkingTrace | null;
  savedConfigPrompt: SavedConfigPrompt | null;
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

// Maps a backend artifact_change `change_type` to the notice type shown when the
// currently-open artifact changes. The backend emits past-tense values
// ("created"/"updated"/"deleted"); "deleted" (and a defensive "delete") maps to
// the delete notice, everything else (incl. "updated"/"created") to update.
export function artifactNoticeTypeFor(
  changeType: string | undefined,
): ArtifactNoticeType {
  return changeType === "deleted" || changeType === "delete"
    ? "delete"
    : "update";
}

function App() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const {
    projects,
    selectedProject,
    selectedProjectId,
    isLoadingProjects,
    projectError,
    selectProject,
    clearSelectedProject,
  } = useProject();

  // All membership-filtered threads for the user (across every accessible
  // project). Drives both the "derive active project from active thread" logic
  // and the per-project starter-thread bootstrap.
  const [threads, setThreads] = useState<Thread[]>([]);

  const [threadId, setThreadId] = useState<string | null>(() =>
    localStorage.getItem("ai-qa-thread-id"),
  );
  const [threadCreationError, setThreadCreationError] = useState<string | null>(
    null,
  );
  const [threadAccessNotice, setThreadAccessNotice] = useState<string | null>(
    null,
  );
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(
    () => localStorage.getItem("ai-qa-sidebar-open") !== "false",
  );
  // Guards against duplicate starter-thread creation under React StrictMode
  // double-invocation and re-renders.
  const creatingThreadRef = useRef(false);
  const ensuredProjectsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setIsSidebarOpen((prev) => {
          const newState = !prev;
          localStorage.setItem("ai-qa-sidebar-open", String(newState));
          return newState;
        });
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setThreadId(null);
      setThreads([]);
      ensuredProjectsRef.current = new Set();
      localStorage.removeItem("ai-qa-thread-id");
      localStorage.removeItem("ai-qa-thread-user-id");
      setThreadCreationError(null);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated && user?.id) {
      const storedThreadUser = localStorage.getItem("ai-qa-thread-user-id");
      if (storedThreadUser && storedThreadUser !== user.id) {
        setThreadId(null);
        setThreads([]);
        ensuredProjectsRef.current = new Set();
        localStorage.removeItem("ai-qa-thread-id");
        localStorage.removeItem("ai-qa-thread-user-id");
        setThreadCreationError(null);
      }
    }
  }, [isAuthenticated, user]);

  // Ensure exactly one starter conversation thread per accessible project.
  // Fetch the membership-filtered thread list once, then create a starter only
  // for projects that have no thread yet. Zero projects => create nothing.
  useEffect(() => {
    const userId = user?.id;
    if (
      !isAuthenticated ||
      !userId ||
      // Admins bypass the workspace shell (AC5) and render the admin dashboard
      // instead, so they must never get starter threads bootstrapped. Without
      // this guard the effect still runs for admins (React runs effects
      // regardless of which JSX branch renders), leaking threads/agent_runs
      // onto a real admin account that test cleanup cannot remove.
      user?.role?.toLowerCase() === "admin" ||
      isLoadingProjects ||
      projects.length === 0 ||
      creatingThreadRef.current ||
      threadCreationError
    ) {
      return;
    }

    creatingThreadRef.current = true;
    (async () => {
      try {
        const existing = await apiFetch<Thread[]>("/threads");
        const projectsWithThread = new Set(
          existing
            .map((t) => t.project_id)
            .filter((id): id is string => Boolean(id)),
        );
        const created: Thread[] = [];
        for (const project of projects) {
          if (
            projectsWithThread.has(project.id) ||
            ensuredProjectsRef.current.has(project.id)
          ) {
            continue;
          }
          // Mark before awaiting so StrictMode double-invocation and re-renders
          // never POST a duplicate starter for the same project.
          ensuredProjectsRef.current.add(project.id);
          const thread = await createThread(userId, project.id);
          created.push(thread);
        }
        const allThreads = [...existing, ...created];
        setThreads(allThreads);

        // Pick a sensible default active thread: keep the persisted thread if it
        // is still accessible, else the most recently updated accessible thread.
        setThreadId((current) => {
          const stored = current ?? localStorage.getItem("ai-qa-thread-id");
          if (stored && allThreads.some((t) => t.id === stored)) {
            return stored;
          }
          const mostRecent = [...allThreads].sort(
            (a, b) =>
              new Date(b.updated_at || b.created_at).getTime() -
              new Date(a.updated_at || a.created_at).getTime(),
          )[0];
          const next = mostRecent?.id ?? null;
          if (next) {
            localStorage.setItem("ai-qa-thread-id", next);
            localStorage.setItem("ai-qa-thread-user-id", userId);
          }
          return next;
        });
      } catch (err) {
        console.error("Failed to ensure project threads:", err);
        setThreadCreationError(
          "Failed to initialize conversation thread. Please check your connection and try again.",
        );
      } finally {
        creatingThreadRef.current = false;
      }
    })();
  }, [
    isAuthenticated,
    user,
    isLoadingProjects,
    projects,
    threadCreationError,
  ]);

  // The active project is derived from the active thread's immutable
  // project_id (Story 7.3/7.5). There is no chooser and no rebind path.
  const activeThread = threads.find((t) => t.id === threadId) ?? null;
  const activeProjectId = activeThread?.project_id ?? null;

  const {
    isConnected,
    error: wsError,
    messageQueue,
    consumeMessages,
    sendMessage,
    onRawEvent,
  } = useWebSocket({
    projectId: isAuthenticated && !threadId ? activeProjectId : null,
    threadId: isAuthenticated ? threadId : null,
  });
  const handleThreadDenied = useCallback(
    (deniedThreadId: string) => {
      // The thread is bound to a project the user can no longer access (or it
      // no longer exists). Drop the stale thread without logging out so the
      // user can pick another conversation or start a new one.
      setThreadId((current) => (current === deniedThreadId ? null : current));
      const stored = localStorage.getItem("ai-qa-thread-id");
      if (stored === deniedThreadId) {
        localStorage.removeItem("ai-qa-thread-id");
        localStorage.removeItem("ai-qa-thread-user-id");
      }
      setThreadAccessNotice(
        "This conversation is no longer available. Your access to its project may have been removed. Pick another conversation or start a new one.",
      );
    },
    [],
  );

  // Artifact tree refresh trigger — incremented when an artifact_change
  // WebSocket event arrives for the currently displayed project.
  const [artifactRefreshTrigger, setArtifactRefreshTrigger] = useState(0);

  // Artifact notice state — shown when a viewed artifact is updated or deleted
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [artifactNotice, setArtifactNotice] = useState<{
    type: ArtifactNoticeType;
    artifactName: string;
  } | null>(null);

  useEffect(() => {
    const unsubscribe = onRawEvent((data) => {
      if (data.type === "artifact_change") {
        const eventProjectId = data.project_id as string | undefined;
        const eventArtifactId = data.artifact_id as string | undefined;
        const changeType = data.change_type as string | undefined;
        
        // Refresh if the event is for the active project (or no project is specified)
        if (!eventProjectId || eventProjectId === activeProjectId) {
          setArtifactRefreshTrigger((prev) => prev + 1);
        }
        
        // Show notice if the changed artifact is currently selected
        if (eventArtifactId && eventArtifactId === selectedArtifact?.id && changeType) {
          const noticeType = artifactNoticeTypeFor(changeType);
          // The event carries no artifact name, but this branch only runs when
          // the changed artifact is the one being viewed, so its name is known.
          setArtifactNotice({
            type: noticeType,
            artifactName: selectedArtifact?.name ?? "Artifact",
          });
        }
      }
    });
    return unsubscribe;
  }, [onRawEvent, activeProjectId, selectedArtifact]);

  const {
    status,
    currentStep,
    messages,
    isLoaded,
    updateFromMessage,
    addUserMessage,
  } = usePipelineState({
    projectId: selectedProjectId,
    threadId,
    onThreadDenied: handleThreadDenied,
  });

  // Derive and lock the active project from the active thread. When the user
  // opens a thread, the provider/sidebar context follows that thread's bound
  // project — no chooser involved.
  useEffect(() => {
    if (!threadId) return;
    const bound = threads.find((t) => t.id === threadId);
    if (bound?.project_id && bound.project_id !== selectedProjectId) {
      selectProject(bound.project_id);
    }
  }, [threadId, threads, selectedProjectId, selectProject]);

  const [aliceState, setAliceState] = useState<AliceState>({
    providerOptions: DEFAULT_PROVIDER_OPTIONS,
    onPremDefaults: undefined,
    modelAssignments: null,
    providerName: "",
    providerEndpoint: "",
    submittedSelection: null,
    thinkingTrace: null,
    savedConfigPrompt: null,
  });
  const [providerConfigPanel, setProviderConfigPanel] = useState<ProviderConfigResponse | null>(null);
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

  // Ref to avoid double-processing the same message from both the live
  // WebSocket queue and the one-shot history sync effect.
  const syncedProjectIdRef = useRef<string | null>(null);
  const processedMsgIds = useRef<Set<string>>(new Set());
  const userScrolledUpRef = useRef(false);

  const resetAliceConfiguration = useCallback(() => {
    setAliceState((prev) => ({
      ...prev,
      submittedSelection: null,
      modelAssignments: null,
      thinkingTrace: null,
    }));
  }, []);

  const handleNewConversationInProject = useCallback(
    (projectId: string) => {
      const userId = user?.id;
      if (!userId) return;
      resetAliceConfiguration();
      setThreadCreationError(null);
      setThreadAccessNotice(null);
      // Create a fresh thread bound to the chosen project and make it active
      // directly — no chooser round-trip.
      createThread(userId, projectId)
        .then((thread) => {
          setThreads((prev) =>
            prev.some((t) => t.id === thread.id) ? prev : [...prev, thread],
          );
          setThreadId(thread.id);
          localStorage.setItem("ai-qa-thread-id", thread.id);
          localStorage.setItem("ai-qa-thread-user-id", userId);
        })
        .catch((err) => {
          console.error("Failed to create new conversation:", err);
          setThreadCreationError(
            "Failed to create a new conversation. Please check your connection and try again.",
          );
        });
    },
    [user, resetAliceConfiguration],
  );

  const hasSentStartRef = useRef(false);

  // Auto-scroll to bottom when new messages arrive (only if user hasn't scrolled up)
  const chatScrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (chatScrollRef.current && !userScrolledUpRef.current) {
      const el = chatScrollRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, aliceState.thinkingTrace, aliceState.modelAssignments]);

  const handleChatScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    userScrolledUpRef.current = !nearBottom;
  }, []);

  useEffect(() => {
    hasSentStartRef.current = false;
  }, [threadId]);

  useEffect(() => {
    if (
      isConnected &&
      currentStep === 1 &&
      status === "start" &&
      threadId &&
      !hasSentStartRef.current
    ) {
      hasSentStartRef.current = true;
      sendMessage({
        type: "start",
        step: 1,
        inputData: {},
      });
    }
  }, [isConnected, currentStep, status, threadId, sendMessage]);

  // Handle WebSocket messages for Alice-specific UI
  const handleAliceMessage = useCallback(
    (message: AgentMessage) => {
      if (message.agentName && message.agentName !== "Alice") return;

      // Provider options from backend — indicates we're back at provider selection step
      // Clear submittedSelection so user can reconfigure
      if (message.metadata?.type === "provider_options") {
        setAliceState((prev) => ({
          ...prev,
          submittedSelection: null,
          modelAssignments: null,
          thinkingTrace: null,
          savedConfigPrompt: null,
          providerOptions: (
            (message.metadata?.options as unknown[]) ?? []
          ).map(normalizeProviderOption),
          onPremDefaults: message.metadata?.on_prem_defaults as
            | { server_url?: string; api_key_configured: boolean }
            | undefined,
        }));
      }

      // Explicit saved-config prompt (Task 4) — offer "use saved / change" without auto-applying
      if (message.metadata?.type === "saved_config_prompt") {
        setAliceState((prev) => ({
          ...prev,
          savedConfigPrompt: message.metadata as unknown as SavedConfigPrompt,
          submittedSelection: null,
          modelAssignments: null,
        }));
      }

      // Model assignments for review
      const resultData =
        (message.metadata?.result as any)?.data || message.metadata;
      if (resultData?.model_assignments) {
        setAliceState((prev) => ({
          ...prev,
          modelAssignments: resultData.model_assignments as ModelAssignment[],
          providerName:
            (
              resultData.configuration as {
                provider?: { provider_name?: string };
              }
            )?.provider?.provider_name || "",
          providerEndpoint: (resultData.provider_endpoint as string) || "",
        }));
      }

      // Thinking Trace
      if (message.metadata?.type === "thinking_trace") {
        const trace = (message.metadata?.trace as ThinkingTrace) || null;
        setAliceState((prev) => ({
          ...prev,
          thinkingTrace: trace,
          // Only promote assignments to modelAssignments when there are actually
          // available models. When available_models is empty (all quota-exceeded /
          // unsupported), Alice has aborted — show only the error trace, never
          // the review table.
          ...(trace?.assignments && trace.assignments.length > 0
              && trace.available_models && trace.available_models.length > 0
            ? { 
                modelAssignments: trace.assignments.map(a => ({
                  agent: a.agent.charAt(0).toUpperCase() + a.agent.slice(1),
                  model: a.model,
                  purpose: a.rationale || "Agent task",
                  rationale: a.rationale || "Agent task",
                })) 
              }
            : {}),
        }));
      }

      // Note: We don't clear modelAssignments on processing anymore
      // to keep the review visible during the entire conversation
    },
    [aliceState.submittedSelection],
  );

  // Handle WebSocket messages for Bob-specific UI
  // FIX RC-1: selectedProject?.confluence_base_url added to dependency array so
  // the closure always captures the current project URL instead of a stale one.
  const handleBobMessage = useCallback(
    (message: AgentMessage, currentProjectUrl?: string | null) => {
      if (message.agentName && message.agentName !== "Bob") return;

      const resultData =
        (message.metadata?.result as any)?.data || message.metadata;

      if (
        resultData?.type === "confirm_parent" ||
        message.metadata?.is_confirm_parent
      ) {
        setBobState((prev) => {
          let newSuggested =
            (resultData?.suggested_page as string) ||
            (message.metadata?.suggested_page as string) ||
            "";
          if (
            newSuggested === "Requirements" ||
            newSuggested === "Requirement" ||
            newSuggested === ""
          ) {
            newSuggested = currentProjectUrl || newSuggested;
          }
          return {
            ...prev,
            isConfirmParent: true,
            suggestedPage: newSuggested,
          };
        });
      } else if (
        message.metadata?.is_review_ready ||
        resultData?.type === "review_ready"
      ) {
        setBobState((prev) => ({
          ...prev,
          isConfirmParent: false,
          isPaginating: true,
          extractedPages:
            (message.metadata?.pages as any) ||
            (resultData?.pages as any) ||
            [],
        }));
      }

      // Thinking Trace
      if (message.metadata?.type === "thinking_trace") {
        setBobState((prev) => ({
          ...prev,
          thinkingTrace: message.metadata?.trace as ThinkingTrace,
        }));
      }
    },
    [],
  );


  useEffect(() => {
    if (messageQueue.length > 0) {
      const messagesToProcess = [...messageQueue];
      messagesToProcess.forEach((msg) => {
        updateFromMessage(msg);
        handleAliceMessage(msg);
        // FIX RC-3: mark as processed so history sync doesn't replay it
        if (msg.id) processedMsgIds.current.add(msg.id);
        handleBobMessage(msg, selectedProject?.confluence_base_url);
      });
      consumeMessages(messagesToProcess.length);
    }
  }, [
    messageQueue,
    updateFromMessage,
    handleAliceMessage,
    handleBobMessage,
    consumeMessages,
    selectedProject,
  ]);

  // Sync state from messages when history is loaded.
  // Replay loaded messages into individual agent states for UI restoration
  useEffect(() => {
    if (
      !isLoaded ||
      syncedProjectIdRef.current === (selectedProject?.id || null)
    )
      return;
    syncedProjectIdRef.current = selectedProject?.id || null;
    messages.forEach((msg) => {
      // FIX RC-3: skip messages already processed from the live queue
      if (msg.id && processedMsgIds.current.has(msg.id)) return;
      handleAliceMessage(msg);
      handleBobMessage(msg, selectedProject?.confluence_base_url);
    });
  }, [isLoaded, selectedProject?.id]);

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
      clearSelectedProject(
        "Your selected project is no longer available. Please choose another project.",
      );
      resetAliceConfiguration();
    }
  }, [clearSelectedProject, wsError, resetAliceConfiguration]);

  // Auto-navigate to Bob when Alice step is completed
  useEffect(() => {
    // Only navigate after conversation is fully loaded
    if (!isLoaded || !selectedProjectId) return;

    if (currentStep === 1 && (status === "completed" || status === "done")) {
      const timer = setTimeout(() => {
        sendMessage({
          type: "navigate",
          step: 2,
          direction: "next",
          agentName: "Bob",
          sender: "user",
          content: "Navigate to Bob",
          messageType: "info",
        });
      }, 2000); // 2 second delay to let user see the completion

      return () => {
        clearTimeout(timer);
      };
    }
  }, [currentStep, status, sendMessage, isLoaded, selectedProjectId]);

  // Handle provider selection
  const handleProviderSelect = useCallback(
    (providerId: string, credentials: Record<string, string>) => {
      if (!selectedProjectId) {
        clearSelectedProject("Select a project before starting the pipeline.");
        return;
      }

      // Find provider name for display
      const provider = aliceState.providerOptions?.find(
        (p) => p.id === providerId,
      );
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
        inputData: {
          provider: providerId,
          credentials,
        },
      });
    },
    [
      sendMessage,
      aliceState.providerOptions,
      selectedProjectId,
      clearSelectedProject,
    ],
  );

  const handleUseSavedConfig = useCallback(() => {
    setAliceState((prev) => ({ ...prev, savedConfigPrompt: null }));
    sendMessage({ type: "start", step: 1, inputData: { use_saved_config: true } });
  }, [sendMessage]);

  const handleInspectConfig = useCallback(() => {
    if (!threadId) return;
    getThreadProviderConfig(threadId)
      .then((cfg) => setProviderConfigPanel(cfg))
      .catch((err) => { console.error("Failed to load provider config:", err); });
  }, [threadId]);

  const handleChangeConfig = useCallback(() => {
    setProviderConfigPanel(null);
    sendMessage({ type: "start", step: 1, inputData: { force_reconfigure: true } });
  }, [sendMessage]);

  // Handle Bob start
  const handleBobStart = useCallback(() => {
    if (!selectedProjectId) return;

    setBobState((prev) => ({ ...prev, submittedMcp: true }));
    // Add user message
    addUserMessage("Start requirements extraction", "info", {
      type: "bob_start",
    });

    sendMessage({
      type: "start",
      step: 2,
      inputData: {
        mcp_pat: bobState.mcpPat,
        confluence_url: selectedProject?.confluence_base_url ?? "",
      },
    });
  }, [
    sendMessage,
    addUserMessage,
    selectedProjectId,
    bobState.mcpPat,
    selectedProject,
  ]);

  const handleApprove = useCallback(
    (updatedAssignments?: Record<string, string>) => {
      if (!selectedProjectId) return;
      // Add user message showing approval action
      addUserMessage("✓ OK", "success");
      sendMessage({
        type: "approve",
        step: currentStep,
        data: {
          assignments: updatedAssignments,
        },
      });
    },
    [sendMessage, addUserMessage, selectedProjectId, currentStep],
  );

  const handleBobApproveParent = useCallback(
    (suggestedPage: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 2,
        data: { confirmed_page_name: suggestedPage },
      });
    },
    [selectedProjectId, sendMessage],
  );

  const handleBobApprove = useCallback(
    (pageId: string, updatedMarkdown: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 2,
        data: {
          action: "approved",
          page_id: pageId,
          markdown: updatedMarkdown,
        },
      });
    },
    [selectedProjectId, sendMessage],
  );

  const handleBobSkip = useCallback(
    (pageId: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 2,
        data: { action: "not_requirement", page_id: pageId },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // The active thread carries an immutable bound project. Provider/Alice UI is
  // shown once that project's context is loaded into ProjectContext.
  const hasConfirmedProject = Boolean(
    activeProjectId &&
    selectedProject &&
    selectedProjectId === activeProjectId,
  );
  // Show ProviderSelector only after Alice has resolved project context.
  const showProviderSelector =
    isAliceStep && hasConfirmedProject && aliceState.providerOptions;
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
    {
      id: 1,
      name: "Alice",
      role: "Config",
      color: "#ec4899",
      colorClass: "bg-[#ec4899]",
    },
    {
      id: 2,
      name: "Bob",
      role: "Requirements",
      color: "#3b82f6",
      colorClass: "bg-[#3b82f6]",
    },
    {
      id: 3,
      name: "Mary",
      role: "Testcases",
      color: "#22c55e",
      colorClass: "bg-[#22c55e]",
    },
    {
      id: 4,
      name: "Sarah",
      role: "Scripts",
      color: "#8b5cf6",
      colorClass: "bg-[#8b5cf6]",
    },
    {
      id: 5,
      name: "Jack",
      role: "Run",
      color: "#f97316",
      colorClass: "bg-[#f97316]",
    },
  ];
  const fallbackAgent = {
    id: 1,
    name: "Alice",
    role: "Config",
    color: "#ec4899",
    colorClass: "bg-[#ec4899]",
  };
  const safeAgent =
    agents[(currentStep ?? 1) - 1] ?? agents[0] ?? fallbackAgent;

  return (
    <div className="h-screen flex bg-[#0f172a] overflow-hidden text-white">
      {/* Sidebar */}
      {isSidebarOpen && (
        <aside className="w-[260px] flex-shrink-0 flex flex-col bg-[#111827] border-r border-[#1f2937] p-3 transition-all duration-300">
          <div className="px-3 py-2 mb-2 font-bold text-base flex items-center gap-2 tracking-wide">
            AI <span className="text-[#3b82f6]">QA Automation</span>
          </div>
          
          {isAuthenticated && (
            <ProjectSidebar 
              currentThreadId={threadId} 
              onSelectThread={(id) => {
                setThreadId(id);
                localStorage.setItem("ai-qa-thread-id", id);
                if (user?.id) localStorage.setItem("ai-qa-thread-user-id", user.id);
                setThreadAccessNotice(null);
              }}
              onNewConversationInProject={handleNewConversationInProject}
              artifactRefreshTrigger={artifactRefreshTrigger}
              onSelectArtifact={setSelectedArtifact}
            />
          )}
        </aside>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-white text-[#0f172a]">
        {/* Top Navigation */}
        <nav className="h-14 border-b border-[#e2e8f0] px-6 flex items-center gap-3 bg-white shadow-sm flex-shrink-0">
          <button
            onClick={() => {
              const newState = !isSidebarOpen;
              setIsSidebarOpen(newState);
              localStorage.setItem("ai-qa-sidebar-open", String(newState));
            }}
            title="Toggle Sidebar Ctrl+B"
            className="p-1.5 -ml-2 mr-1 text-[#64748b] hover:bg-[#f1f5f9] rounded-md transition-colors flex items-center justify-center focus:outline-none"
          >
            <PanelLeft className="w-5 h-5" />
          </button>

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
              <span className="text-xs text-[#64748b] mr-2">{user.name}</span>
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

        <div className="flex-1 flex flex-col overflow-hidden relative">
          {/* Artifact Notice */}
          {artifactNotice && (
            <div className="px-5 py-2 bg-white border-b border-[#e2e8f0] flex-shrink-0">
              <ArtifactNotice
                type={artifactNotice.type}
                artifactName={artifactNotice.artifactName}
                onDismiss={() => setArtifactNotice(null)}
              />
            </div>
          )}
          
          {/* Topbar */}
          <div className="px-5 py-3.5 border-b border-[#e2e8f0] flex items-center gap-3 bg-white flex-shrink-0">
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
                Step {currentStep} of 5
                {isProcessing && " · Testing connection..."}
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
            {isAliceStep && threadId && (
              <button
                onClick={handleInspectConfig}
                aria-label="Inspect provider configuration"
                title="Provider Configuration"
                data-testid="inspect-config-btn"
                className="p-1.5 rounded-lg text-[#64748b] hover:bg-[#f1f5f9] hover:text-[#0f172a] transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            )}
          </div>

          {/* Provider Config Panel (inspect modal) */}
          {providerConfigPanel && (
            <ProviderConfigPanel
              config={providerConfigPanel}
              onChangeConfig={handleChangeConfig}
              onClose={() => setProviderConfigPanel(null)}
            />
          )}

          {/* Error display */}
          {wsError && (
            <div className="bg-[#fee2e2] text-[#ef4444] px-4 py-3 rounded text-sm mb-6 flex justify-between items-center shadow-sm border border-[#f87171]/20">
              {wsError}
            </div>
          )}
          {threadCreationError && (
            <div className="bg-[#fee2e2] text-[#ef4444] px-4 py-3 rounded text-sm mb-6 flex justify-between items-center shadow-sm border border-[#f87171]/20">
              <span>{threadCreationError}</span>
              <button
                onClick={() => {
                  setThreadId(null);
                  localStorage.removeItem("ai-qa-thread-id");
                  localStorage.removeItem("ai-qa-thread-user-id");
                  setThreadCreationError(null);
                }}
                className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors text-xs font-semibold"
              >
                Retry
              </button>
            </div>
          )}
          {threadAccessNotice && (
            <div
              role="status"
              data-testid="thread-access-notice"
              className="bg-[#fffbeb] text-[#b45309] px-4 py-3 rounded text-sm mb-6 flex justify-between items-center gap-3 shadow-sm border border-[#fcd34d]"
            >
              <span>{threadAccessNotice}</span>
              <button
                onClick={() => setThreadAccessNotice(null)}
                className="px-3 py-1 bg-[#f59e0b] text-white rounded hover:bg-[#d97706] transition-colors text-xs font-semibold flex-shrink-0"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Chat Content - Scrollable container (hidden when artifact preview is open) */}
          <div ref={chatScrollRef} onScroll={handleChatScroll} className={`flex-1 bg-[#f8fafc] overflow-y-auto max-h-[calc(100vh-120px)]${selectedArtifact ? " hidden" : ""}`}>
            <div className="p-5 flex flex-col gap-4 min-h-0">
              {/* Alice info message: loading / error / no-access. The project
                  is bound implicitly from the active thread, so there is no
                  project chooser. */}
              {!hasConfirmedProject &&
                (isLoadingProjects || projectError || projects.length === 0) && (
                  <div className="w-[40%] min-w-[18rem] max-w-xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                      Alice
                    </div>
                    <div className="p-4 text-sm leading-relaxed bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm">
                      {isLoadingProjects ? (
                        <p>Loading your accessible projects...</p>
                      ) : projectError ? (
                        <p>{projectError}</p>
                      ) : (
                        <p>
                          You do not have access to any project yet. Please
                          contact an administrator to assign you to a project.
                        </p>
                      )}
                    </div>
                  </div>
                )}


              {/* Saved-config prompt (Task 4) — explicit use/change affordance */}
              {hasConfirmedProject && aliceState.savedConfigPrompt && !aliceState.submittedSelection && (
                <div className="self-start w-[50%] min-w-0">
                  <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">Alice</div>
                  <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed space-y-3">
                    <p>
                      You have a saved provider configuration for this project:{" "}
                      <span className="font-semibold">
                        {aliceState.savedConfigPrompt.saved_config?.provider_name}
                      </span>
                      {aliceState.savedConfigPrompt.saved_config?.endpoint && (
                        <span className="text-[#64748b] ml-1">
                          ({aliceState.savedConfigPrompt.saved_config.endpoint})
                        </span>
                      )}
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={handleUseSavedConfig}
                        data-testid="use-saved-config-btn"
                        className="px-4 py-2 rounded-full bg-[#3b82f6] text-white text-sm font-medium hover:bg-[#2563eb] transition-colors"
                      >
                        Use saved configuration
                      </button>
                      <button
                        onClick={() =>
                          setAliceState((prev) => ({
                            ...prev,
                            savedConfigPrompt: null,
                            providerOptions:
                              prev.savedConfigPrompt?.options.map(normalizeProviderOption) ??
                              prev.providerOptions,
                          }))
                        }
                        data-testid="choose-different-provider-btn"
                        className="px-4 py-2 rounded-full border border-[#e2e8f0] text-sm text-[#64748b] hover:bg-[#f8fafc] transition-colors"
                      >
                        Choose a different provider
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Alice Provider Selector - shown after project resolution */}
              {hasConfirmedProject && aliceState.providerOptions.length > 0 && !aliceState.savedConfigPrompt && (
                <ProviderSelector
                  options={aliceState.providerOptions}
                  onPremDefaults={aliceState.onPremDefaults}
                  onSelect={handleProviderSelect}
                  disabled={
                    !isConnected ||
                    !!aliceState.submittedSelection ||
                    !selectedProjectId
                  }
                  submittedSelection={aliceState.submittedSelection}
                  enabledProviders={selectedProject?.enabled_providers}
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
                <ThinkingBubble
                  key={`trace-${aliceState.thinkingTrace.connection_status}-${aliceState.thinkingTrace.available_models?.length || 0}`}
                  trace={aliceState.thinkingTrace}
                  title="Alice's thought"
                  isCompleted={!aliceState.thinkingTrace.available_models?.length}
                />
              )}

              {/* Model Assignment Review - Show BEFORE user action messages */}
              {!!aliceState.modelAssignments && (
                <ModelAssignmentReview
                  provider={aliceState.providerName}
                  endpoint={aliceState.providerEndpoint}
                  assignments={aliceState.modelAssignments}
                  availableModels={aliceState.thinkingTrace?.available_models}
                  unavailableModels={aliceState.thinkingTrace?.unavailable_models}
                  onApprove={handleApprove}
                  disabled={!isConnected || status === "error"}
                />
              )}

              {/* Unified Message History - Chronological Order */}
              {[...messages]
                .sort(
                  (a, b) =>
                    new Date(a.timestamp).getTime() -
                    new Date(b.timestamp).getTime(),
                )
                .filter((msg) => {
                  // Skip processing/thinking messages that are transient
                  const content = msg.content?.toLowerCase() || "";
                  if (content === "processing" || content === "review_request")
                    return false;
                  if (
                    content.includes("testing connection") &&
                    !content.includes("success")
                  )
                    return false;
                  // Skip provider options messages (rendered via ProviderSelector component)
                  if (msg.metadata?.type === "provider_options") return false;
                  // Skip thinking trace messages (rendered via ThinkingBubble component)
                  if (msg.metadata?.type === "thinking_trace") return false;
                  // Skip model assignments messages (rendered via ModelAssignmentReview component)
                  if (msg.metadata?.model_assignments) return false;
                  // Skip project selection message because it is rendered inline to preserve chat flow:
                  // Alice asks for project -> user chooses project -> Alice asks for provider.
                  if (
                    msg.sender === "user" &&
                    selectedProject &&
                    hasConfirmedProject &&
                    content === selectedProject.name.toLowerCase()
                  )
                    return false;
                  // Keep "successfully connected" messages visible as regular messages
                  // Skip "done", "error", "start" status messages
                  if (
                    content === "done" ||
                    content === "error" ||
                    content === "start"
                  )
                    return false;
                  // Keep "AI Provider Configuration complete" visible until navigation
                  // Skip navigation messages (handled by state update)
                  if (msg.metadata?.type === "navigation") return false;
                  // Skip redundant confirm_parent messages (old text and new text)
                  if (
                    msg.metadata?.is_confirm_parent ||
                    content.includes(
                      "contains all requirements, is it correct?",
                    )
                  )
                    return false;
                  // DO NOT skip bob_start message anymore, we will render MCP input right before it
                  return true;
                })
                .map((msg) => {
                  if (msg.metadata?.type === "bob_start") {
                    return (
                      <Fragment key={msg.id}>
                        {/* Bob MCP Input rendered right before the user start message */}
                        {isBobStep && (
                          <div className="w-[85%] max-w-4xl self-start mb-4">
                            <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                              Bob
                            </div>
                            <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                              <p className="text-sm font-medium">
                                Please enter your MCP key to continue
                              </p>
                              <div className="flex gap-3">
                                <input
                                  type="password"
                                  placeholder="Enter MCP API Key..."
                                  value={bobState.mcpPat}
                                  onChange={(e) =>
                                    setBobState((prev) => ({
                                      ...prev,
                                      mcpPat: e.target.value,
                                    }))
                                  }
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
                          <div className="text-[11px] font-semibold mb-1 text-[#64748b] text-right">
                            You
                          </div>
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
                      className={`w-[40%] min-w-0 ${msg.sender === "user" ? "self-end" : "self-start"}`}
                    >
                      <div
                        className={`text-[11px] font-semibold mb-1 ${msg.sender === "user" ? "text-[#64748b] text-right" : "text-[#3b82f6]"}`}
                      >
                        {msg.sender === "user"
                          ? "You"
                          : msg.agentName || msg.sender}
                      </div>
                      <div
                        className={`p-4 text-sm leading-relaxed ${msg.sender === "user" ? "bg-[#3b82f6] text-white rounded-2xl rounded-br-sm" : "bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a]"}`}
                      >
                        {msg.content}
                      </div>
                    </div>
                  );
                })}

              {/* If Bob MCP Input hasn't been rendered yet because bob_start doesn't exist */}
              {!messages.some((m) => m.metadata?.type === "bob_start") &&
                isBobStep &&
                (status === "start" || bobState.submittedMcp) && (
                  <div className="w-[85%] max-w-4xl self-start mt-4">
                    <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                      Bob
                    </div>
                    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                      <p className="text-sm font-medium">
                        Please enter your MCP key to continue
                      </p>
                      <div className="flex gap-3">
                        <input
                          type="password"
                          placeholder="Enter MCP API Key..."
                          value={bobState.mcpPat}
                          onChange={(e) =>
                            setBobState((prev) => ({
                              ...prev,
                              mcpPat: e.target.value,
                            }))
                          }
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
                <ThinkingBubble
                  trace={(bobState as any).thinkingTrace}
                  title="Bob's thought"
                />
              )}

              {/* Bob Parent Page Confirmation */}
              {isBobStep &&
                status === "review_request" &&
                bobState.isConfirmParent && (
                  <div className="w-[85%] max-w-4xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                      Bob
                    </div>
                    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                      <p className="text-sm font-medium text-gray-700 leading-relaxed">
                        I found the below link contains all requirements, is it
                        correct? If not, please input the correct one.
                      </p>
                      <div className="flex gap-3">
                        <input
                          type="text"
                          placeholder="Enter the correct page URL..."
                          value={bobState.suggestedPage}
                          onChange={(e) =>
                            setBobState((prev) => ({
                              ...prev,
                              suggestedPage: e.target.value,
                            }))
                          }
                          className="flex-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent"
                        />
                        <button
                          onClick={() =>
                            handleBobApproveParent(bobState.suggestedPage)
                          }
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
              {isBobStep &&
                status === "review_request" &&
                bobState.isPaginating &&
                bobState.extractedPages && (
                  <div className="w-[85%] max-w-5xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                      Bob
                    </div>
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

          {/* Artifact Preview — replaces chat content when an artifact is selected */}
          {selectedArtifact && (
            <ArtifactPreview
              artifact={selectedArtifact}
              onClose={() => setSelectedArtifact(null)}
            />
          )}

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
