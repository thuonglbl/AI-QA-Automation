import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePipelineState } from "@/hooks/usePipelineState";
import { useAuth } from "@/hooks/useAuth";
import { createThread, type Thread } from "@/lib/threads";
import { apiFetch } from "@/lib/api";
import { MessageTime, NowMessageTime } from "@/components/MessageTime";
import { ProviderSelector } from "@/components/ProviderSelector";
import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
import { ProcessingIndicator } from "@/components/ProcessingIndicator";
import { LoginPage } from "@/components/auth/LoginPage";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { ProjectAdminDashboard } from "@/components/admin/ProjectAdminDashboard";
import { UserBadge, effectiveRoles } from "@/components/auth/UserBadge";
import { ThinkingBubble } from "@/components/ThinkingBubble";
import { ProjectSidebar } from "@/components/conversations/ProjectSidebar";
import { ArtifactNotice, type ArtifactNoticeType } from "@/components/artifacts/ArtifactNotice";
import { ArtifactPreview } from "@/components/artifacts/ArtifactPreview";
import type { Artifact } from "@/components/conversations/ProjectSidebar";
import { MaryReviewPanel } from "@/components/agents/MaryReviewPanel";
import { SarahInputSelection } from "@/components/agents/SarahInputSelection";
import { SarahInputsForm, type SarahInputsRequest } from "@/components/agents/SarahInputsForm";
import { InteractiveMFAPrompt } from "@/components/agents/InteractiveMFAPrompt";
import { SarahScriptReviewPanel } from "@/components/agents/SarahScriptReviewPanel";
import {
  JackInputSelection,
  type ProjectEnvironment,
  type CapturedSessionSlot,
  type JackRunConfig,
} from "@/components/agents/JackInputSelection";
import { JackExecutionReport } from "@/components/agents/JackExecutionReport";
import type { MaryReviewCase, TestCaseInput, ScriptReviewItem, ScriptValidationError } from "@/types/testcase";
import type { ScriptInput } from "@/types/script";
import type { ExecutionSummary } from "@/types/execution";
import { useProject } from "@/hooks/useProject";
import type {
  ProviderOption,
  ProviderId,
  AuthMethod,
  SecurityLevel,
  CredentialField,
  ModelAssignment,
  ThinkingTrace,
  SavedConfigPrompt,
  ProviderBenchmark,
} from "@/types/provider";
import type { AgentMessage } from "@/types/pipeline";
import { ArrowDown, KeyRound, LogOut, PanelLeft, Settings, Shield } from "lucide-react";
import { SessionMatrixPanel } from "@/components/sessions/SessionMatrixPanel";
import { listSessions } from "@/lib/sessions";
import { ErrorFeedback } from "@/components/ErrorFeedback";
import { mapBackendError } from "@/lib/error-messages";
import { AppVersion } from "@/components/AppVersion";

// Default provider options - shown immediately without waiting for WebSocket.
// Order is authoritative and mirrors the backend PROVIDER_OPTIONS:
// On-Premises, Claude SSO, Browser Use, Claude (API key), Gemini, OpenAI.
const DEFAULT_PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: "on-premises",
    name: "On-Premises",
    description: "Internal infrastructure · Company API key",
    qualityRank: 5,
    securityLevel: "highest",
    authMethod: "api_key",
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
  {
    id: "claude-sso",
    name: "Anthropic / Claude (SSO)",
    description: "Cloud · Enterprise SSO login",
    qualityRank: 2,
    securityLevel: "enterprise",
    authMethod: "sso",
    credentialFields: [],
  },
  {
    id: "browser-use-cloud",
    name: "Browser Use Cloud",
    description: "Cloud · Personal API key",
    qualityRank: 1,
    securityLevel: "cloud",
    authMethod: "api_key",
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
    description: "Cloud · Personal API key",
    qualityRank: 2,
    securityLevel: "good",
    authMethod: "api_key",
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
    authMethod: "api_key",
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
    authMethod: "api_key",
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
  "claude-sso",
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
  const authMethod =
    (o.authMethod as AuthMethod | undefined) ??
    (o.auth_method as AuthMethod | undefined) ??
    "api_key";
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
    authMethod,
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
  /** Provider ids that already have a stored key — clicking them skips the prompt. */
  configuredProviders: string[];
  /** Provider whose last connection failed (invalid key) — re-prompt for a new key. */
  invalidProvider: string | null;
  /** Bumped on every connection failure so the re-prompt clears even on repeat
   *  failures of the SAME provider (invalidProvider value alone wouldn't change). */
  invalidAttempt: number;
  benchmark: ProviderBenchmark | null;
}

interface BobState {
  mcpPat: string;
  requirementUrl: string | undefined;
  isConfirmParent: boolean;
  suggestedPage: string;
  pageMetadata: any;
  submittedMcp?: boolean;
  // After extraction, Bob asks for ONE Confluence page id / Jira ticket id.
  selectIdPrompt: boolean;
  selectedIdInput: string;
  // Point 5: interactive clarification loop. While clarifyPrompt is true Bob is
  // waiting for the user to answer (or skip) the open quality questions for one file.
  clarifyPrompt: boolean;
  clarifyInput: string;
  clarifyData: {
    pageId: string;
    pageTitle: string;
    sourceUrl: string;
    points: { category: string; message: string; blocking: boolean }[];
  } | null;
  error: string | null;
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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
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
  const [sessionsPanelOpen, setSessionsPanelOpen] = useState<boolean>(false);
  // Epic 23: role-aware in-app navigation (no router). `null` => derive the initial
  // view from the user's role set; an explicit value is a user-driven view switch.
  const [activeView, setActiveView] = useState<
    "workspace" | "project_admin" | "admin" | null
  >(null);
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
      !effectiveRoles(user).has("standard") ||
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

  // Task 4.4: Self-echo suppression for the currently-open artifact.
  // Stores the artifact_id and change_type of the last self-initiated mutation.
  const suppressSelfEchoRef = useRef<{ artifactId: string; type: string; timer?: number } | null>(null);

  const handleSelfMutation = useCallback((artifactId: string, type: "updated" | "deleted") => {
    if (suppressSelfEchoRef.current?.timer) {
      window.clearTimeout(suppressSelfEchoRef.current.timer);
    }
    suppressSelfEchoRef.current = {
      artifactId,
      type,
      timer: window.setTimeout(() => {
        suppressSelfEchoRef.current = null;
      }, 3000),
    };
  }, []);

  // Clear suppression flag if selection changes
  useEffect(() => {
    if (suppressSelfEchoRef.current?.timer) {
      window.clearTimeout(suppressSelfEchoRef.current.timer);
    }
    suppressSelfEchoRef.current = null;
  }, [selectedArtifact]);

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
          // Task 4.4: Suppress self-echo for own edits/deletes
          if (
            suppressSelfEchoRef.current?.artifactId === eventArtifactId &&
            suppressSelfEchoRef.current?.type === changeType
          ) {
            if (suppressSelfEchoRef.current.timer) {
              window.clearTimeout(suppressSelfEchoRef.current.timer);
            }
            suppressSelfEchoRef.current = null; // Consume it
            return;
          }

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
    loadedThreadId,
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
    configuredProviders: [],
    invalidProvider: null,
    invalidAttempt: 0,
    benchmark: null,
  });
  const isAliceStep = currentStep === 1;

  const [bobState, setBobState] = useState<BobState>({
    mcpPat: localStorage.getItem("mcp_pat") || "",
    requirementUrl: undefined,
    isConfirmParent: false,
    suggestedPage: "",
    pageMetadata: null,
    submittedMcp: false,
    selectIdPrompt: false,
    selectedIdInput: "",
    clarifyPrompt: false,
    clarifyInput: "",
    clarifyData: null,
    error: null,
  });
  // The single id Bob handed off, carried to Mary's auto-start.
  const [marySelectedId, setMarySelectedId] = useState<string>("");
  const [maryState, setMaryState] = useState<{
    testCases: MaryReviewCase[] | null;
    // Risk-based test-design clarification loop: while clarifyPrompt is true Mary is
    // waiting for the user to answer (or skip) one unclear point before generating.
    clarifyPrompt: boolean;
    clarifyInput: string;
  }>({
    testCases: null,
    clarifyPrompt: false,
    clarifyInput: "",
  });
  const isBobStep = currentStep === 2;
  const isMaryStep = currentStep === 3;
  const isSarahStep = currentStep === 4;
  const isJackStep = currentStep === 5;
  // True from the moment "Confirm & Run" is clicked until Jack starts running (status leaves
  // review_request) or bounces back with an error — disables the run button + shows a spinner.
  const [jackRunStarting, setJackRunStarting] = useState(false);

  const [sarahState, setSarahState] = useState<{
    testCases: TestCaseInput[] | null;
    scripts: ScriptReviewItem[] | null;
    validationErrors: Record<number, ScriptValidationError[]>;
    inputsRequest: SarahInputsRequest | null;
    sessions: CapturedSessionSlot[];
  }>({
    testCases: null,
    scripts: null,
    validationErrors: {},
    inputsRequest: null,
    sessions: [],
  });

  // Jack (step 5) input-selection + execution state (14.1/14.2/14.4).
  const [jackState, setJackState] = useState<{
    scripts: ScriptInput[] | null;
    environments: ProjectEnvironment[];
    appRoles: string[];
    sessions: CapturedSessionSlot[];
    summary: ExecutionSummary | null;
  }>({
    scripts: null,
    environments: [],
    appRoles: [],
    sessions: [],
    summary: null,
  });

  // Ref to avoid double-processing the same message from both the live
  // WebSocket queue and the one-shot history sync effect. Keyed on the loaded
  // thread so each conversation restores its panels exactly once on switch.
  const syncedThreadIdRef = useRef<string | null>(null);
  const processedMsgIds = useRef<Set<string>>(new Set());
  const userScrolledUpRef = useRef(false);

  // Interactive MFA prompt state
  const [mfaRequest, setMfaRequest] = useState<{
    sessionId: string;
    environment: string;
    role: string;
    projectId: string;
  } | null>(null);

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
  // Separate guard so Mary's auto-start doesn't collide with Alice's step-1 guard.
  const hasSentMaryStartRef = useRef(false);
  // Separate guard for Sarah's step-4 auto-start.
  const hasSentSarahStartRef = useRef(false);
  // Separate guard for Jack's step-5 auto-start.
  const hasSentJackStartRef = useRef(false);
  // Set when Bob hands off with a blank id (skip test case generation): the
  // Bob-DONE auto-nav effect reads this to route to Sarah (step 4) instead of
  // Mary (step 3). A ref (not state) avoids racing the status→done flip.
  const bobSkipToSarahRef = useRef(false);

  // Task 6.1: Track previous message count to detect NEW arrivals (not in-place updates).
  // When a new message arrives, force-scroll unconditionally and reset userScrolledUpRef so
  // the user is considered "at bottom". In-place updates (same count) respect the guard.
  // Task 6.2: chatBottomRef is a sentinel div that we call scrollIntoView on next-frame —
  // reliable even when async content (markdown/ReviewContent/thinking panels) renders after.
  // Task 6.3: NOT coupled to artifactRefreshTrigger (separate effect key) so artifact refresh
  // never resets scroll position — preserves Story 10.7 invariant.
  const prevMessageCountRef = useRef(0);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  // Point 1: when a new message arrives while the user has scrolled UP to read,
  // we no longer yank them down — we surface a floating "New message" pill instead.
  const [hasNewMessage, setHasNewMessage] = useState(false);

  // Auto-scroll on new messages ONLY when the user is already at the bottom; if they
  // scrolled up to read, preserve their position and flag a new message (point 1).
  useEffect(() => {
    const newMessage = messages.length > prevMessageCountRef.current;
    prevMessageCountRef.current = messages.length;

    if (newMessage) {
      if (userScrolledUpRef.current) {
        // Reading older messages: don't disrupt — show the floating button.
        setHasNewMessage(true);
      } else {
        requestAnimationFrame(() => {
          chatBottomRef.current?.scrollIntoView({ block: "end" });
        });
      }
    } else if (chatScrollRef.current && !userScrolledUpRef.current) {
      // Streaming update (aliceState / thinkingTrace): only scroll if not scrolled up
      requestAnimationFrame(() => {
        chatBottomRef.current?.scrollIntoView({ block: "end" });
      });
    }
  }, [messages, aliceState.thinkingTrace, aliceState.modelAssignments]);

  const handleChatScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    userScrolledUpRef.current = !nearBottom;
    // Back at the bottom: the user has caught up — clear the new-message flag.
    if (nearBottom) setHasNewMessage(false);
  }, []);

  // Click handler for the floating "New message" pill: jump to the latest message.
  const scrollToLatestMessage = useCallback(() => {
    userScrolledUpRef.current = false;
    setHasNewMessage(false);
    requestAnimationFrame(() => {
      chatBottomRef.current?.scrollIntoView({ block: "end" });
    });
  }, []);

  // Task 6.4: Reset userScrolledUpRef when switching threads so the new thread
  // always starts at the bottom (chat re-shows after a preview close too).
  // Review P2 fix: also reset prevMessageCountRef so the new-message detector compares
  // against this thread's own message count, not the previous thread's. Otherwise switching
  // from a longer thread to a shorter one mis-classifies the next real message as "not new"
  // (count <= stale prior count) and skips the AC4 force-scroll. Resetting to 0 makes the
  // new thread's first load read as "new", landing it at the bottom.
  useEffect(() => {
    hasSentStartRef.current = false;
    hasSentMaryStartRef.current = false;
    hasSentSarahStartRef.current = false;
    hasSentJackStartRef.current = false;
    bobSkipToSarahRef.current = false;
    // Clear the id Bob handed off so it never leaks into the next thread's
    // Mary auto-start (each thread carries its own selected id server-side).
    setMarySelectedId("");
    userScrolledUpRef.current = false;
    prevMessageCountRef.current = 0;
    // Clear the floating "New message" pill so a flag raised in the previous
    // thread can't persist into a freshly-loaded one (point 1 / F5).
    setHasNewMessage(false);
    // Full conversation isolation: reset every agent panel and the processed-id
    // dedup set so the previous thread/project cannot bleed into this one, and so
    // the new thread's history is replayed (not skipped) by the restore effect.
    resetAliceConfiguration();
    setBobState({
      mcpPat: localStorage.getItem("mcp_pat") || "",
      requirementUrl: undefined,
      isConfirmParent: false,
      suggestedPage: "",
      pageMetadata: null,
      submittedMcp: false,
      selectIdPrompt: false,
      selectedIdInput: "",
      clarifyPrompt: false,
      clarifyInput: "",
      clarifyData: null,
      error: null,
    });
    setMaryState({ testCases: null, clarifyPrompt: false, clarifyInput: "" });
    setSarahState({
      testCases: null,
      scripts: null,
      validationErrors: {},
      inputsRequest: null,
      sessions: [],
    });
    setJackState({ scripts: null, environments: [], appRoles: [], sessions: [], summary: null });
    setJackRunStarting(false);
    processedMsgIds.current.clear();
  }, [threadId, resetAliceConfiguration]);

  // Review P3 fix: the chat container is display:none (`hidden`) while an artifact preview
  // is open, so a new message arriving during the preview cannot scroll its sentinel into
  // view. When the preview closes (selectedArtifact -> null) the chat re-shows — scroll to
  // the bottom on the next frame so the missed message is visible (honors AC4 "always show
  // newest"). The userScrolledUpRef guard preserves position when the user had scrolled up
  // and nothing new arrived (a new message resets the flag in the scroll effect above).
  useEffect(() => {
    if (selectedArtifact) return;
    if (userScrolledUpRef.current) return;
    requestAnimationFrame(() => {
      chatBottomRef.current?.scrollIntoView({ block: "end" });
    });
  }, [selectedArtifact]);

  useEffect(() => {
    if (
      isConnected &&
      currentStep === 1 &&
      status === "start" &&
      threadId &&
      !hasSentStartRef.current
    ) {
      if (sendMessage({
        type: "start",
        step: 1,
        inputData: {},
      })) {
        hasSentStartRef.current = true;
      }
    }
  }, [isConnected, currentStep, status, threadId, sendMessage]);

  // Auto-start Mary on entry to step 3, carrying the id Bob selected. The id is
  // also persisted server-side (mary_selected_id.json), so this is a convenience.
  useEffect(() => {
    if (
      isConnected &&
      currentStep === 3 &&
      status === "start" &&
      threadId &&
      !hasSentMaryStartRef.current
    ) {
      if (sendMessage({
        type: "start",
        step: 3,
        inputData: marySelectedId ? { selected_id: marySelectedId } : {},
      })) {
        hasSentMaryStartRef.current = true;
      }
    }
  }, [isConnected, currentStep, status, threadId, sendMessage, marySelectedId]);

  // Handle WebSocket messages for Alice-specific UI
  const handleAliceMessage = useCallback(
    (message: AgentMessage) => {
      if (message.agentName && message.agentName !== "Alice") return;

      // Rebuild the read-only submitted provider selection from its persisted
      // marker (set during history replay). Processed in timeline order, so a
      // later provider_options (re-prompt) below still clears it correctly.
      if (message.metadata?.type === "provider_selection") {
        const providerId = message.metadata.providerId as string | undefined;
        const providerName = message.metadata.providerName as string | undefined;
        if (providerId) {
          setAliceState((prev) => ({
            ...prev,
            submittedSelection: {
              providerId,
              providerName: providerName || providerId,
              credentials: {},
            },
          }));
        }
        return;
      }

      // Provider options from backend — indicates we're back at provider selection step
      // Clear submittedSelection so user can reconfigure
      if (message.metadata?.type === "provider_options") {
        setAliceState((prev) => ({
          ...prev,
          submittedSelection: null,
          modelAssignments: null,
          thinkingTrace: null,
          savedConfigPrompt: null,
          invalidProvider: null,
          invalidAttempt: 0,
          providerOptions: (
            (message.metadata?.options as unknown[]) ?? []
          ).map(normalizeProviderOption),
          onPremDefaults: message.metadata?.on_prem_defaults as
            | { server_url?: string; api_key_configured: boolean }
            | undefined,
          configuredProviders:
            (message.metadata?.configured_providers as string[] | undefined) ?? [],
        }));
      }

      // Connection test failed (e.g. a stored key is no longer valid): drop the
      // read-only submitted view and flag the provider so the selector re-prompts
      // for a fresh key with the "invalid key" placeholder.
      if (
        message.metadata?.type === "connection_test" &&
        message.metadata?.status === "failed"
      ) {
        setAliceState((prev) => ({
          ...prev,
          invalidProvider:
            prev.submittedSelection?.providerId ?? prev.invalidProvider,
          invalidAttempt: prev.invalidAttempt + 1,
          submittedSelection: null,
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
          // Connection succeeded — clear any stale invalid-key flag.
          invalidProvider: null,
          modelAssignments: resultData.model_assignments as ModelAssignment[],
          providerName:
            (
              resultData.configuration as {
                provider?: { provider_name?: string };
              }
            )?.provider?.provider_name || "",
          providerEndpoint: (resultData.provider_endpoint as string) || "",
          benchmark: resultData.benchmark || null,
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
                key: a.agent,
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

      if (message.messageType === "error") {
        setBobState((prev) => ({
          ...prev,
          submittedMcp: false,
          error: message.content,
        }));
        return;
      }

      // The persisted bob_start marker means MCP was already submitted — rebuild
      // submittedMcp on replay so a restored thread greys out the key input
      // instead of re-prompting for a key already provided.
      if (message.metadata?.type === "bob_start") {
        setBobState((prev) =>
          prev.submittedMcp ? prev : { ...prev, submittedMcp: true },
        );
        return;
      }

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
      } else if (message.metadata?.type === "clarify_request") {
        // Point 5: Bob is asking the user to clarify unclear points for one file.
        // The question text renders as a normal Bob bubble; this drives the reply panel.
        const rawPoints = message.metadata?.points;
        setBobState((prev) => ({
          ...prev,
          isConfirmParent: false,
          selectIdPrompt: false,
          clarifyPrompt: true,
          clarifyInput: "",
          clarifyData: {
            pageId: String(message.metadata?.page_id ?? ""),
            pageTitle: String(message.metadata?.page_title ?? ""),
            sourceUrl: String(message.metadata?.source_url ?? ""),
            points: Array.isArray(rawPoints)
              ? (rawPoints as {
                category: string;
                message: string;
                blocking: boolean;
              }[])
              : [],
          },
        }));
      } else if (message.metadata?.is_select_id) {
        // Extraction (and any clarification) done; Bob asks for one id to generate from.
        setBobState((prev) => ({
          ...prev,
          isConfirmParent: false,
          clarifyPrompt: false,
          clarifyData: null,
          selectIdPrompt: true,
        }));
      }
      // Blank-id skip: Bob's DONE message carries skip_to_sarah so the Bob-DONE
      // auto-nav effect routes to Sarah (step 4) instead of Mary (step 3).
      if (message.metadata?.skip_to_sarah) {
        bobSkipToSarahRef.current = true;
        setBobState((prev) => ({ ...prev, selectIdPrompt: false }));
      }
      // Bob's thinking_trace is no longer stored in bobState — it renders inline
      // in the message map (point 2), in chronological order.
    },
    [],
  );

  // Handle WebSocket messages for Mary-specific UI
  const handleMaryMessage = useCallback((message: AgentMessage) => {
    if (message.agentName && message.agentName !== "Mary") return;
    if (message.metadata?.type === "test_clarify_request") {
      // Mary is asking the author to clarify an unclear point before generating.
      setMaryState((prev) => ({
        ...prev,
        testCases: null,
        clarifyPrompt: true,
        clarifyInput: "",
      }));
      return;
    }
    if (message.metadata?.type === "test_case_review") {
      const testCases = (message.metadata.test_cases as MaryReviewCase[]) ?? [];
      // The review list means clarification is over — close the clarify panel.
      setMaryState((prev) => ({ ...prev, testCases, clarifyPrompt: false }));
    }
  }, []);

  // Handle WebSocket messages for Sarah-specific UI
  const handleSarahMessage = useCallback((message: AgentMessage) => {
    if (message.agentName && message.agentName !== "Sarah") return;
    if (message.metadata?.type === "test_case_selection") {
      const testCases = (message.metadata.test_cases as TestCaseInput[]) ?? [];
      setSarahState((prev) => ({ ...prev, testCases, scripts: null, inputsRequest: null }));
    } else if (message.metadata?.type === "sarah_inputs_request") {
      // Sarah needs the target environment URL before it can drive the real app with
      // browser-use. The captured login session is rehydrated server-side, so no Chrome
      // path / CDP URL is asked here.
      const m = message.metadata;
      setSarahState((prev) => ({
        ...prev,
        testCases: null,
        scripts: null,
        inputsRequest: {
          needsUrl: !!m.needs_url,
          environments:
            (m.environments as { name: string; url: string; login_type?: string }[] | undefined) ?? [],
        },
      }));
    } else if (message.metadata?.type === "script_review") {
      // Present-all transport (13.5): replace scripts list; clear input-selection.
      // Also clear validationErrors — new payload = new generation, stale errors are invalid.
      const scripts = (message.metadata.scripts as ScriptReviewItem[]) ?? [];
      setSarahState((prev) => ({
        ...prev,
        scripts,
        testCases: null,
        validationErrors: {},
        inputsRequest: null,
      }));
    } else if (message.metadata?.type === "script_validation_error") {
      // 13.6 AC2: set per-script validation errors WITHOUT touching the scripts list.
      // The panel's Edit buffer must NOT be reset — that's the load-bearing AC1 mechanism.
      const idx = message.metadata.script_index as number;
      const errors = (message.metadata.errors as ScriptValidationError[]) ?? [];
      setSarahState((prev) => ({
        ...prev,
        validationErrors: { ...prev.validationErrors, [idx]: errors },
      }));
    }
  }, []);

  // When Sarah asks for its inputs, load the current user's captured sessions so the form
  // can show per-role capture status and offer an inline Import.
  const refreshSarahSessions = useCallback(async () => {
    if (!selectedProjectId) return;
    try {
      const matrix = await listSessions(selectedProjectId);
      setSarahState((prev) => ({
        ...prev,
        sessions: matrix.captured.map((s) => ({
          environment: s.environment,
          role: s.role,
          expires_at: s.expires_at,
        })),
      }));
    } catch {
      // Non-fatal: the form still works (capture status just shows as not-captured).
    }
  }, [selectedProjectId]);

  useEffect(() => {
    if (sarahState.inputsRequest) void refreshSarahSessions();
  }, [sarahState.inputsRequest, refreshSarahSessions]);

  // Handle WebSocket messages for Jack-specific UI (14.1 selection, 14.2/14.4 summary)
  const handleJackMessage = useCallback((message: AgentMessage) => {
    if (message.agentName && message.agentName !== "Jack") return;
    // Any Jack error, a re-emitted selection panel, or the final summary means the run is no
    // longer in the "starting" limbo — re-enable the Confirm & Run button.
    if (
      message.messageType === "error" ||
      message.metadata?.type === "script_selection" ||
      message.metadata?.type === "execution_summary"
    ) {
      setJackRunStarting(false);
    }
    if (message.metadata?.type === "script_selection") {
      const scripts = (message.metadata.scripts as ScriptInput[]) ?? [];
      const environments = (message.metadata.environments as ProjectEnvironment[]) ?? [];
      const appRoles = (message.metadata.app_roles as string[]) ?? [];
      const sessions = (message.metadata.sessions as CapturedSessionSlot[]) ?? [];
      setJackState((prev) => ({
        ...prev,
        scripts,
        environments,
        appRoles,
        sessions,
        summary: null,
      }));
    } else if (message.metadata?.type === "execution_summary") {
      const m = message.metadata;
      const summary: ExecutionSummary = {
        run_id: (m.run_id as string | null) ?? null,
        total: (m.total as number) ?? 0,
        passed: (m.passed as number) ?? 0,
        failed: (m.failed as number) ?? 0,
        errors: (m.errors as number) ?? 0,
        skipped: (m.skipped as number) ?? 0,
        duration_ms: (m.duration_ms as number) ?? 0,
        browsers: (m.browsers as string[]) ?? [],
        unavailable_browsers:
          (m.unavailable_browsers as { label: string; reason: string }[]) ?? [],
        report_artifact_id: (m.report_artifact_id as string | null) ?? null,
      };
      setJackState((prev) => ({ ...prev, summary, scripts: null }));
    }
  }, []);

  const handleSystemMessage = useCallback((msg: AgentMessage) => {
    if (msg.sender === "system" && msg.metadata?.action === "MFA_REQUIRED") {
      setMfaRequest({
        sessionId: msg.metadata.session_id as string,
        environment: msg.metadata.environment as string,
        role: msg.metadata.role as string,
        projectId: msg.metadata.project_id as string,
      });
    }
  }, []);

  useEffect(() => {
    if (messageQueue.length > 0) {
      const messagesToProcess = [...messageQueue];
      messagesToProcess.forEach((msg) => {
        updateFromMessage(msg);
        handleAliceMessage(msg);
        // FIX RC-3: mark as processed so history sync doesn't replay it
        if (msg.id) processedMsgIds.current.add(msg.id);
        handleBobMessage(msg, selectedProject?.confluence_base_url);
        handleMaryMessage(msg);
        handleSarahMessage(msg);
        handleJackMessage(msg);
        handleSystemMessage(msg);
      });
      consumeMessages(messagesToProcess.length);
    }
  }, [
    messageQueue,
    updateFromMessage,
    handleAliceMessage,
    handleBobMessage,
    handleMaryMessage,
    handleSarahMessage,
    handleJackMessage,
    handleSystemMessage,
    consumeMessages,
    selectedProject,
  ]);

  // Sync state from messages when history is loaded.
  // Replay loaded messages into individual agent states for UI restoration.
  // Keyed on loadedThreadId (set only once the matching thread's messages are in
  // state) so restoration runs exactly once per loaded thread — including two
  // threads in the same project — without racing the stale isLoaded flag during
  // a switch.
  useEffect(() => {
    if (loadedThreadId === null) return;
    if (syncedThreadIdRef.current === loadedThreadId) return;
    syncedThreadIdRef.current = loadedThreadId;
    messages.forEach((msg) => {
      // FIX RC-3: skip messages already processed from the live queue
      if (msg.id && processedMsgIds.current.has(msg.id)) return;
      handleAliceMessage(msg);
      handleBobMessage(msg, selectedProject?.confluence_base_url);
      // Restore Mary/Sarah review-panel state on reload / thread re-select,
      // consistent with the live-queue effect (and with Bob above). Without
      // these, the test-case / script review panels vanish after a refresh.
      handleMaryMessage(msg);
      handleSarahMessage(msg);
      handleJackMessage(msg);
      // Mark restored ids processed so a later live echo/reconnect replay of an
      // already-restored message isn't handled a second time (symmetric with the
      // live-queue effect's FIX RC-3 bookkeeping).
      if (msg.id) processedMsgIds.current.add(msg.id);
    });
  }, [
    loadedThreadId,
    messages,
    handleAliceMessage,
    handleBobMessage,
    handleMaryMessage,
    handleSarahMessage,
    handleJackMessage,
    selectedProject?.confluence_base_url,
  ]);

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

  // Auto-navigate when Bob reaches DONE (mirror of the Alice→Bob effect). A blank
  // id skips Mary: route straight to Sarah (step 4), which reuses existing approved
  // test cases. Otherwise route to Mary (step 3) for test-case generation.
  useEffect(() => {
    if (!isLoaded || !selectedProjectId) return;
    if (currentStep === 2 && (status === "completed" || status === "done")) {
      const timer = setTimeout(() => {
        // Read the ref at fire time, not effect-run time: the status→done message
        // arrives just before Bob's skip_to_sarah handoff message, so the flag may
        // only be set in the brief window before this 2s timer fires.
        const skipToSarah = bobSkipToSarahRef.current;
        sendMessage({
          type: "navigate",
          step: skipToSarah ? 4 : 3,
          direction: "next",
          agentName: skipToSarah ? "Sarah" : "Mary",
          sender: "user",
          content: skipToSarah ? "Navigate to Sarah" : "Navigate to Mary",
          messageType: "info",
        });
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [currentStep, status, sendMessage, isLoaded, selectedProjectId]);

  // Auto-start Sarah when step 4 is reached and Sarah is in START state.
  // The user arrives here via the "Proceed to Sarah" button (12.4). Sarah
  // needs no user input to begin loading approved test cases.
  useEffect(() => {
    if (
      isConnected &&
      currentStep === 4 &&
      status === "start" &&
      threadId &&
      !hasSentSarahStartRef.current
    ) {
      if (sendMessage({
        type: "start",
        step: 4,
        inputData: {},
      })) {
        hasSentSarahStartRef.current = true;
      }
    }
  }, [isConnected, currentStep, status, threadId, sendMessage]);

  // Auto-start Jack when step 5 is reached and Jack is in START state.
  // The user arrives here via the "Proceed to Jack" button. Jack needs no user
  // input to begin loading approved scripts.
  useEffect(() => {
    if (
      isConnected &&
      currentStep === 5 &&
      status === "start" &&
      threadId &&
      !hasSentJackStartRef.current
    ) {
      if (sendMessage({
        type: "start",
        step: 5,
        inputData: {},
      })) {
        hasSentJackStartRef.current = true;
      }
    }
  }, [isConnected, currentStep, status, threadId, sendMessage]);

  // Mary approve: send index-addressable approve to backend
  const handleMaryApprove = useCallback(
    (index: number) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 3,
        data: { action: "approved", test_case_index: index },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Mary reject: send index-addressable reject to backend
  const handleMaryReject = useCallback(
    (index: number, feedback: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "reject",
        step: 3,
        feedback,
        data: { test_case_index: index },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Mary clarify: answer (or skip) the current test-design clarification question.
  // Routed as an "approve" on step 3 — the backend reads the action while in its
  // clarify phase. Mirrors Bob's clarification reply.
  const handleMaryClarifyAnswer = useCallback(
    (action: "clarify_answer" | "skip", answer: string) => {
      if (!selectedProjectId) return;
      const trimmed = answer.trim();
      if (action === "clarify_answer" && !trimmed) return;
      addUserMessage(action === "skip" ? "Skip this question" : trimmed);
      // Hide the panel while Mary processes; a follow-up question (or the test-case
      // review) re-opens the right UI.
      setMaryState((prev) => ({ ...prev, clarifyPrompt: false, clarifyInput: "" }));
      sendMessage({
        type: "approve",
        step: 3,
        data: { action, answer: trimmed },
      });
    },
    [selectedProjectId, sendMessage, addUserMessage],
  );

  // Sarah confirm: send selected artifact ids as approve with input-selection action
  const handleSarahConfirm = useCallback(
    (selectedIds: string[]) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 4,
        data: { action: "confirm_inputs", selected_artifact_ids: selectedIds },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Sarah skip: nothing selected → bypass script generation and go straight to Jack
  // (step 5), which reuses existing approved scripts. Mirrors the "Proceed to Jack" nav.
  const handleSarahSkipToJack = useCallback(() => {
    sendMessage({
      type: "navigate",
      step: 5,
      direction: "next",
      agentName: "Jack",
      sender: "user",
      content: "Navigate to Jack",
      messageType: "info",
    });
  }, [sendMessage]);

  // Jack confirm: send selected script ids + run config (URL/env/role/browsers) (14.1/14.2/14.4)
  const handleJackConfirm = useCallback(
    (selectedIds: string[], config: JackRunConfig) => {
      if (!selectedProjectId) return;
      setJackRunStarting(true);
      sendMessage({
        type: "approve",
        step: 5,
        data: {
          action: "confirm_inputs",
          selected_artifact_ids: selectedIds,
          target_url: config.targetUrl,
          environment: config.environment,
          role: config.role,
          browsers: config.browsers,
        },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Sarah inputs submit: re-start step 4 carrying the target environment NAME and URL so
  // the browser-use exploration can run on the real app. The environment NAME is the
  // authoritative key the backend uses to resolve the captured session (sessions are keyed
  // by env name); the URL drives explore navigation. The captured login session is
  // rehydrated server-side, so no Chrome path / CDP URL is sent.
  const handleSarahInputsSubmit = useCallback(
    ({ environment, targetUrl }: { environment: string; targetUrl: string }) => {
      if (!selectedProjectId) return;
      setSarahState((prev) => ({ ...prev, inputsRequest: null }));
      sendMessage({
        type: "start",
        step: 4,
        inputData: { target_url: targetUrl, environment },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Sarah script-review approve (index-addressable, 13.5)
  const handleSarahApprove = useCallback(
    (index: number, editedContent?: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 4,
        data: {
          action: "approved",
          script_index: index,
          // 13.6 AC3: thread the edited content so the backend can validate + save it.
          // When undefined (no edit), the backend takes the back-compat path (saves original).
          ...(editedContent !== undefined ? { script_content: editedContent } : {}),
        },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Sarah script-review skip: routes through approve with action="skip" (WS only has approve/reject)
  const handleSarahSkip = useCallback(
    (index: number) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "approve",
        step: 4,
        data: { action: "skip", script_index: index },
      });
    },
    [selectedProjectId, sendMessage],
  );

  // Sarah script-review reject (index-addressable, 13.5)
  const handleSarahReject = useCallback(
    (index: number, feedback: string) => {
      if (!selectedProjectId) return;
      sendMessage({
        type: "reject",
        step: 4,
        feedback,
        data: { script_index: index },
      });
    },
    [selectedProjectId, sendMessage],
  );

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

      // Persist a SECRET-FREE marker (no credentials) so the submitted selection
      // can be rebuilt when the conversation is reloaded — otherwise a restored
      // thread re-shows the provider list as if nothing was chosen. Hidden from
      // the chat list (filtered by metadata.type); the ProviderSelector renders
      // the read-only choice instead.
      addUserMessage(`Selected provider: ${providerName || providerId}`, "info", {
        type: "provider_selection",
        providerId,
        providerName: providerName || providerId,
      });

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
      addUserMessage,
      aliceState.providerOptions,
      selectedProjectId,
      clearSelectedProject,
    ],
  );

  const handleUseSavedConfig = useCallback(() => {
    setAliceState((prev) => ({ ...prev, savedConfigPrompt: null }));
    sendMessage({ type: "start", step: 1, inputData: { use_saved_config: true } });
  }, [sendMessage]);

  // Handle Bob start
  const handleBobStart = useCallback(() => {
    if (!selectedProjectId) return;

    const finalMcpPat = bobState.mcpPat;
    const finalReqUrl = bobState.requirementUrl ?? selectedProject?.confluence_base_url ?? "";

    if (finalMcpPat) {
      localStorage.setItem("mcp_pat", finalMcpPat);
    }

    setBobState((prev) => ({ ...prev, submittedMcp: true, error: null, requirementUrl: finalReqUrl }));
    // Add user message
    addUserMessage("Start requirements extraction", "info", {
      type: "bob_start",
    });

    sendMessage({
      type: "start",
      step: 2,
      inputData: {
        mcp_pat: finalMcpPat,
        confluence_url: finalReqUrl,
      },
    });
  }, [
    sendMessage,
    addUserMessage,
    selectedProjectId,
    bobState.mcpPat,
    bobState.requirementUrl,
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
      const trimmed = suggestedPage.trim();
      // Echo the user's choice as a chat bubble (mirrors handleBobSelectId /
      // handleBobClarifyAnswer). Without this, no user bubble is ever created
      // for the submitted parent-page URL, so it disappears when the
      // confirm-parent panel unmounts (review_request→processing) with nothing
      // left in the chat history.
      addUserMessage(trimmed ? trimmed : "Skip");
      setBobState((prev) => ({ ...prev, isConfirmParent: false }));
      // Blank → skip extraction and go straight to test cases (Mary); a value →
      // (re)scope extraction to that page and its child pages.
      sendMessage({
        type: "approve",
        step: 2,
        data: trimmed ? { confirmed_page_name: trimmed } : { action: "skip" },
      });
    },
    [selectedProjectId, sendMessage, addUserMessage],
  );

  // Auto-confirm the parent page since the user already entered the URL in step 1.
  useEffect(() => {
    if (isBobStep && status === "review_request" && bobState.isConfirmParent && isConnected) {
      handleBobApproveParent(bobState.suggestedPage);
    }
  }, [isBobStep, status, bobState.isConfirmParent, isConnected, bobState.suggestedPage, handleBobApproveParent]);

  // Resume an extraction interrupted by a server restart. The "resume" flag tells
  // Bob's handle_start to replay from the persisted parent (already-saved pages are
  // reused server-side), so no URL/parent/MCP key is re-entered.
  const handleBobContinue = useCallback(() => {
    if (!selectedProjectId) return;
    addUserMessage("Continue extraction", "info");
    sendMessage({
      type: "start",
      step: 2,
      inputData: { resume: true },
    });
  }, [selectedProjectId, sendMessage, addUserMessage]);

  // After extraction, the user submits ONE Confluence page id or Jira ticket id.
  // Bob resolves it (reads+saves a Jira ticket, or reuses an already-saved page),
  // persists the choice for Mary, and hands off.
  const handleBobSelectId = useCallback(
    (id: string) => {
      const trimmed = id.trim();
      if (!selectedProjectId) return;
      if (trimmed) {
        // A real id is the Mary path: clear any stale skip flag so blank/non-blank
        // submissions are symmetric (defensive — Bob isn't re-enterable today).
        bobSkipToSarahRef.current = false;
        setMarySelectedId(trimmed);
        addUserMessage(trimmed);
      } else {
        // Blank id = skip test case generation. Bob hands off to Sarah (signalled
        // via skip_to_sarah on its DONE message), which reuses existing test cases.
        addUserMessage("Skip test case generation");
      }
      // Hide the select-id panel immediately so the user cannot submit again
      // while waiting for the server response (mirrors clarify panel behavior).
      setBobState((prev) => ({ ...prev, selectIdPrompt: false, selectedIdInput: "" }));
      sendMessage({
        type: "approve",
        step: 2,
        data: { action: "select_id", id: trimmed },
      });
    },
    [selectedProjectId, sendMessage, addUserMessage],
  );

  // Point 5: send a clarification answer (or skip this file) for the current file.
  // Bob routes by phase, so both actions go over the same approve channel. The
  // clarify question bundles all of a file's unclear points, so skipping is
  // per-file (there is no per-point skip).
  const handleBobClarifyAnswer = useCallback(
    (action: "clarify_answer" | "skip_file", answer: string) => {
      if (!selectedProjectId) return;
      const pageId = bobState.clarifyData?.pageId ?? "";
      const trimmed = answer.trim();
      if (action === "clarify_answer" && !trimmed) return;
      addUserMessage(action === "skip_file" ? "Skip this file" : trimmed);
      // Hide the panel while Bob processes; a follow-up clarify_request (or the
      // select-id prompt) re-opens the right UI.
      setBobState((prev) => ({ ...prev, clarifyPrompt: false, clarifyInput: "" }));
      sendMessage({
        type: "approve",
        step: 2,
        data: { action, page_id: pageId, answer: trimmed },
      });
    },
    [selectedProjectId, bobState.clarifyData, sendMessage, addUserMessage],
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
  // Earliest bob_start marker (by timestamp) — the chat list collapses any later
  // duplicates onto this one so the MCP input renders exactly once.
  const firstBobStartId =
    [...messages]
      .sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      )
      .find((m) => m.metadata?.type === "bob_start")?.id ?? null;

  // Show login page if not authenticated
  if (!isAuthenticated && !isLoading) {
    return <LoginPage />;
  }

  // Epic 23: role-aware navigation. Multi-role users land on the workspace by
  // default with header links to the dashboards they're entitled to; a user whose
  // ONLY role is admin/project_admin (no standard) lands on that dashboard. An
  // explicit `activeView` (header link / "Back to workspace") overrides the default.
  const roleSet = effectiveRoles(user);
  const canAdmin = roleSet.has("admin");
  const canProjectAdmin = canAdmin || roleSet.has("project_admin");
  const defaultView: "workspace" | "project_admin" | "admin" = roleSet.has(
    "standard",
  )
    ? "workspace"
    : canAdmin
      ? "admin"
      : roleSet.has("project_admin")
        ? "project_admin"
        : "workspace";
  const currentView = activeView ?? defaultView;
  const backToWorkspace = () => setActiveView("workspace");

  if (isAuthenticated && currentView === "admin" && canAdmin) {
    return (
      <AdminDashboard
        onBackToWorkspace={backToWorkspace}
        onNavigateToProjectAdmin={canProjectAdmin ? () => setActiveView("project_admin") : undefined}
      />
    );
  }

  if (isAuthenticated && currentView === "project_admin" && canProjectAdmin) {
    return (
      <ProjectAdminDashboard
        onBackToWorkspace={backToWorkspace}
        onNavigateToAdmin={canAdmin ? () => setActiveView("admin") : undefined}
      />
    );
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
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-white focus:text-[#0f172a] focus:font-semibold focus:rounded-md focus:shadow-md"
      >
        Skip to main content
      </a>
      {/* Sidebar */}
      {isSidebarOpen && (
        <aside className="w-[540px] flex-shrink-0 flex flex-col bg-[#111827] border-r border-[#1f2937] p-3 transition-all duration-300">
          <div className="px-3 py-2 mb-2 font-bold text-base flex items-center gap-2 tracking-wide">
            AI <span className="text-[#3b82f6]">QA Automation</span>
          </div>

          {isAuthenticated && (
            <ProjectSidebar
              currentThreadId={threadId}
              activeProjectId={activeProjectId}
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
      <main id="main-content" className="flex-1 flex flex-col min-w-0 bg-white text-[#0f172a]">
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
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap select-none ${currentStep === agent.id
                  ? "bg-[#3b82f6] text-white"
                  : "bg-transparent text-[#64748b]"
                  }`}
              >
                {agent.id}. {agent.name} — {agent.role}
              </span>
            ))}
          </div>
          <div className="ml-auto flex items-center">
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center hover:opacity-80 transition-opacity focus:outline-none"
                title="User menu"
              >
                {user && <UserBadge user={user} displayRole="User" />}
              </button>

              {userMenuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setUserMenuOpen(false)}
                  />
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg py-1 border border-slate-200 z-50">
                    {canAdmin && (
                      <button
                        onClick={() => {
                          setActiveView("admin");
                          setUserMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                      >
                        <Shield className="w-4 h-4" />
                        Admin Dashboard
                      </button>
                    )}
                    {canProjectAdmin && (
                      <button
                        onClick={() => {
                          setActiveView("project_admin");
                          setUserMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                      >
                        <Settings className="w-4 h-4" />
                        Project Admin Dashboard
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setSessionsPanelOpen(true);
                        setUserMenuOpen(false);
                      }}
                      disabled={!selectedProjectId}
                      className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <KeyRound className="w-4 h-4" />
                      Test Accounts
                    </button>
                    <div className="h-px bg-slate-200 my-1" />
                    <div className="px-4 py-2 text-xs text-slate-500">
                      Version: <AppVersion className="inline" />
                    </div>
                    <button
                      onClick={() => {
                        logout();
                        setUserMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <LogOut className="w-4 h-4" />
                      Logout
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </nav>
        {selectedProjectId && (
          <SessionMatrixPanel
            projectId={selectedProjectId}
            projectName={selectedProject?.name}
            open={sessionsPanelOpen}
            onClose={() => {
              setSessionsPanelOpen(false);
              // A session may have just been captured. Re-sync Jack's per-role run gate so the
              // "No captured session" warning clears live — jackState.sessions otherwise only
              // refreshes when Jack re-emits the script-selection panel (reject/restart).
              if (selectedProjectId) {
                void listSessions(selectedProjectId)
                  .then((matrix) =>
                    setJackState((prev) => ({
                      ...prev,
                      sessions: matrix.captured.map((s) => ({
                        environment: s.environment,
                        role: s.role,
                        expires_at: s.expires_at,
                      })),
                    })),
                  )
                  .catch(() => undefined);
              }
            }}
          />
        )}

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
                  className={`w-2 h-2 rounded-full transition-colors ${idx + 1 < currentStep
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
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold ${status === "start"
                ? "bg-[#f1f5f9] text-[#64748b]"
                : status === "processing"
                  ? "bg-[#fffbeb] text-[#d97706]"
                  : status === "review_request"
                    ? "bg-[#eff6ff] text-[#2563eb]"
                    : "bg-[#f0fdf4] text-[#16a34a]"
                }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${status === "start"
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

          {/* Chat Content - Scrollable container (hidden when artifact preview is open).
              Wrapped in a relative box so the floating "New message" pill (point 1) can
              anchor to the chat viewport; the wrapper hides together with the chat. */}
          <div className={`relative flex-1 flex flex-col min-h-0${selectedArtifact ? " hidden" : ""}`}>
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
                        <NowMessageTime />
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
                    <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">
                      Alice
                      <MessageTime
                        timestamp={
                          messages.find(
                            (m) => m.metadata?.type === "saved_config_prompt",
                          )?.timestamp
                        }
                        fallbackToNow
                      />
                    </div>
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
                    configuredProviders={aliceState.configuredProviders}
                    invalidProvider={aliceState.invalidProvider}
                    invalidAttempt={aliceState.invalidAttempt}
                    messageTimestamp={
                      messages.find(
                        (m) => m.metadata?.type === "provider_options",
                      )?.timestamp
                    }
                    selectionTimestamp={
                      messages.find(
                        (m) => m.metadata?.type === "provider_selection",
                      )?.timestamp
                    }
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
                    timestamp={
                      messages.find(
                        (m) =>
                          m.metadata?.type === "thinking_trace" &&
                          m.agentName !== "Bob",
                      )?.timestamp
                    }
                    isCompleted={!aliceState.thinkingTrace.available_models?.length}
                  />
                )}

                {/* Model Assignment Review - shown if we successfully connected */}
                {aliceState.modelAssignments && (
                  <ModelAssignmentReview
                    provider={aliceState.providerName}
                    endpoint={aliceState.providerEndpoint}
                    assignments={aliceState.modelAssignments}
                    availableModels={
                      aliceState.thinkingTrace?.available_models ?? undefined
                    }
                    unavailableModels={
                      aliceState.thinkingTrace?.unavailable_models ?? undefined
                    }
                    onApprove={handleApprove}
                    disabled={!isConnected || status === "error"}
                    disabledReason={!isConnected ? "Waiting for connection..." : (status === "error" ? "Cannot proceed due to an error." : undefined)}
                    benchmark={aliceState.benchmark}
                    messageTimestamp={
                      messages.find((m) => m.metadata?.model_assignments)
                        ?.timestamp
                    }
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
                    // Skip empty-content messages (e.g. provider_options carriers,
                    // including persisted ones whose metadata didn't round-trip).
                    if (!msg.content || msg.content.trim() === "") return false;
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
                    // Skip Mary's per-item test-case review carrier: its markdown dump
                    // ("## Test Case X of Y …") is redundant — the MaryReviewPanel below
                    // renders the same case with approve/reject controls.
                    if (msg.metadata?.type === "test_case_review") return false;
                    // Skip the secret-free provider-selection marker (rebuilds the
                    // read-only ProviderSelector on reload; never a chat bubble).
                    if (msg.metadata?.type === "provider_selection") return false;
                    // Collapse duplicate bob_start markers (stale dupes accumulated
                    // by earlier sessions): keep only the first so the MCP input and
                    // "Start requirements extraction" bubble render exactly once.
                    if (
                      msg.metadata?.type === "bob_start" &&
                      firstBobStartId !== null &&
                      msg.id !== firstBobStartId
                    )
                      return false;
                    // Alice's streaming trace renders via the fixed ThinkingBubble below;
                    // Bob's one-shot "Extract from MCP: done" trace renders INLINE in
                    // chronological order (point 2), so only skip non-Bob traces here.
                    if (
                      msg.metadata?.type === "thinking_trace" &&
                      msg.agentName !== "Bob"
                    )
                      return false;
                    // Point 3: is_select_id only drives the inline select-id input
                    // (rendered separately below); its carrier text is redundant.
                    if (msg.metadata?.is_select_id) return false;
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
                    // Filter out Bob's MCP/URL validation error bubble so it can show on the form instead
                    if (msg.agentName === "Bob" && msg.messageType === "error" && isBobStep && status === "start") return false;
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
                                <MessageTime timestamp={msg.timestamp} />
                              </div>
                              <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                                <div className="flex flex-col gap-4">
                                  <div>
                                    <p className="text-sm font-medium mb-1">
                                      Please enter your MCP key (required)
                                    </p>
                                    <input
                                      type="password"
                                      value={bobState.mcpPat}
                                      onChange={(e) =>
                                        setBobState((prev) => ({
                                          ...prev,
                                          mcpPat: e.target.value,
                                        }))
                                      }
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          e.preventDefault();
                                          if (bobState.mcpPat && isConnected && (!bobState.submittedMcp || status === "start")) handleBobStart();
                                        }
                                      }}
                                      disabled={bobState.submittedMcp && status !== "start"}
                                      className={`w-full rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent ${(bobState.submittedMcp && status !== "start") || (localStorage.getItem("mcp_pat") && !bobState.error) ? "bg-gray-100 text-gray-500" : ""}`}
                                    />
                                  </div>
                                  <div>
                                    <p className="text-sm font-medium mb-1">
                                      Please enter parent requirement URL on Confluence (leave blank to skip)
                                    </p>
                                    <input
                                      type="text"
                                      value={bobState.requirementUrl ?? selectedProject?.confluence_base_url ?? ""}
                                      onChange={(e) =>
                                        setBobState((prev) => ({
                                          ...prev,
                                          requirementUrl: e.target.value,
                                        }))
                                      }
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          e.preventDefault();
                                          if (bobState.mcpPat && isConnected && (!bobState.submittedMcp || status === "start")) handleBobStart();
                                        }
                                      }}
                                      disabled={bobState.submittedMcp && status !== "start"}
                                      className="w-full rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
                                    />
                                  </div>
                                  {bobState.error && (
                                    <div className="text-red-500 text-sm font-medium mt-1">
                                      {bobState.error}
                                    </div>
                                  )}
                                  <div className="flex justify-end mt-2">
                                    {(!bobState.submittedMcp || status === "start") && (
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
                            </div>
                          )}
                          {/* The bob_start message itself */}
                          <div className="max-w-[75%] w-fit min-w-0 self-end">
                            <div className="text-[11px] font-semibold mb-1 text-[#64748b] text-right">
                              You
                              <MessageTime timestamp={msg.timestamp} />
                            </div>
                            <div className="p-4 text-sm leading-relaxed break-words bg-[#3b82f6] text-white rounded-2xl rounded-br-sm">
                              {msg.content}
                            </div>
                          </div>
                        </Fragment>
                      );
                    }

                    // Point 2: Bob's thinking trace renders inline at its chronological
                    // position (right after the conversions, before the quality summary).
                    if (msg.metadata?.type === "thinking_trace") {
                      return (
                        <ThinkingBubble
                          key={msg.id}
                          trace={msg.metadata?.trace as ThinkingTrace}
                          title="Bob's thought"
                          timestamp={msg.timestamp}
                        />
                      );
                    }

                    // Point 5: Bob's clarification question carries a "Clarify: <file>"
                    // title so the user knows which requirement it concerns.
                    if (msg.metadata?.type === "clarify_request") {
                      return (
                        <div key={msg.id} className="w-[85%] max-w-4xl self-start">
                          <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                            Bob
                            <MessageTime timestamp={msg.timestamp} />
                          </div>
                          <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm p-5 flex flex-col gap-2">
                            <p className="text-sm font-semibold text-gray-800">
                              Clarify: {String(msg.metadata?.page_title ?? "")}
                            </p>
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </p>
                          </div>
                        </div>
                      );
                    }

                    // Mary's risk-based test-design clarification question.
                    if (msg.metadata?.type === "test_clarify_request") {
                      return (
                        <div key={msg.id} className="w-[85%] max-w-4xl self-start">
                          <div className="text-[11px] font-semibold mb-1 text-[#22c55e]">
                            Mary
                            <MessageTime timestamp={msg.timestamp} />
                          </div>
                          <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm p-5 flex flex-col gap-2">
                            <p className="text-sm font-semibold text-gray-800">
                              Clarify before writing test cases
                            </p>
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </p>
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={msg.id}
                        // User bubbles hug their content and grow leftward up to
                        // 75% while staying pinned to the right edge (self-end), so
                        // a long Confluence URL extends left instead of overflowing.
                        // Agent bubbles keep the fixed 40% column. min-w-0 lets the
                        // flex item shrink so break-words can wrap long URLs.
                        className={`min-w-0 ${msg.sender === "user" ? "max-w-[75%] w-fit self-end" : "w-[40%] self-start"}`}
                      >
                        <div
                          className={`text-[11px] font-semibold mb-1 ${msg.sender === "user" ? "text-[#64748b] text-right" : "text-[#3b82f6]"}`}
                        >
                          {msg.sender === "user"
                            ? "You"
                            : msg.agentName || msg.sender}
                          <MessageTime timestamp={msg.timestamp} />
                        </div>
                        {msg.messageType === "error" ? (
                          <div className="bg-white border border-red-200 rounded-2xl rounded-bl-sm p-4 shadow-sm">
                            <ErrorFeedback
                              error={mapBackendError({
                                message: msg.content,
                                type: String(msg.metadata?.type || ""),
                                code: String(msg.metadata?.code || ""),
                              })}
                            />
                          </div>
                        ) : (
                          <div
                            className={`p-4 text-sm leading-relaxed break-words ${msg.sender === "user" ? "bg-[#3b82f6] text-white rounded-2xl rounded-br-sm" : "bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a]"}`}
                          >
                            {msg.content}
                          </div>
                        )}
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
                        <NowMessageTime />
                      </div>
                      <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                        <div className="flex flex-col gap-4">
                          <div>
                            <p className="text-sm font-medium mb-1">
                              Please enter your MCP key (required)
                            </p>
                            <input
                              type="password"
                              value={bobState.mcpPat}
                              onChange={(e) =>
                                setBobState((prev) => ({
                                  ...prev,
                                  mcpPat: e.target.value,
                                }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  if (bobState.mcpPat && isConnected && !bobState.submittedMcp) handleBobStart();
                                }
                              }}
                              disabled={bobState.submittedMcp}
                              className={`w-full rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent ${bobState.submittedMcp || (localStorage.getItem("mcp_pat") && !bobState.error) ? "bg-gray-100 text-gray-500" : ""}`}
                            />
                          </div>
                          <div>
                            <p className="text-sm font-medium mb-1">
                              Please enter parent requirement URL on Confluence (leave blank to skip)
                            </p>
                            <input
                              type="text"
                              value={bobState.requirementUrl ?? selectedProject?.confluence_base_url ?? ""}
                              onChange={(e) =>
                                setBobState((prev) => ({
                                  ...prev,
                                  requirementUrl: e.target.value,
                                }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  if (bobState.mcpPat && isConnected && !bobState.submittedMcp) handleBobStart();
                                }
                              }}
                              disabled={bobState.submittedMcp}
                              className="w-full rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
                            />
                          </div>
                          {bobState.error && (
                            <div className="text-red-500 text-sm font-medium mt-1">
                              {bobState.error}
                            </div>
                          )}
                          <div className="flex justify-end mt-2">
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
                    </div>
                  )}

                {/* Resume affordance: the reconciler flagged an interrupted run as
                  resumable (metadata.resume_available on the persisted system message),
                  so offer a one-click Continue that replays from the persisted parent.
                  Already-extracted pages are reused on the backend. */}
                {isBobStep &&
                  status === "start" &&
                  messages.some((m) => m.metadata?.resume_available) && (
                    <div className="w-[85%] max-w-4xl self-start mt-4">
                      <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                        Bob
                        <NowMessageTime />
                      </div>
                      <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                        <p className="text-sm font-medium text-gray-700 leading-relaxed">
                          The previous extraction was interrupted. Continue to resume from
                          where it stopped — already-extracted pages are reused, so only the
                          remaining pages are processed.
                        </p>
                        <div>
                          <button
                            onClick={handleBobContinue}
                            disabled={!isConnected}
                            className="bg-[#3b82f6] text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            Continue
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                {/* Bob's thinking trace now renders inline within the message map
                  above (point 2) so it appears in chronological order. */}


                {/* Bob single-id selection (replaces the old per-page review panel).
                  All extracted pages are auto-saved; the user picks ONE id to
                  generate test cases from. */}
                {isBobStep &&
                  status === "review_request" &&
                  bobState.selectIdPrompt && (
                    <div className="w-[85%] max-w-4xl self-start">
                      <div className="text-[11px] font-semibold mb-1 text-[#3b82f6]">
                        Bob
                        <MessageTime
                          timestamp={
                            messages.find((m) => m.metadata?.is_select_id)
                              ?.timestamp
                          }
                          fallbackToNow
                        />
                      </div>
                      <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                        <p className="text-sm font-medium text-gray-700 leading-relaxed">
                          Requirements saved. Enter 1 Confluence page id or Jira
                          ticket id to generate test cases, or leave blank to skip
                          and reuse existing test cases.
                        </p>
                        <div className="flex gap-3">
                          <input
                            type="text"
                            value={bobState.selectedIdInput}
                            onChange={(e) =>
                              setBobState((prev) => ({
                                ...prev,
                                selectedIdInput: e.target.value,
                              }))
                            }
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                handleBobSelectId(bobState.selectedIdInput);
                              }
                            }}
                            placeholder="Leave blank to skip and reuse existing test cases"
                            className="flex-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent"
                          />
                          <button
                            onClick={() =>
                              handleBobSelectId(bobState.selectedIdInput)
                            }
                            disabled={!isConnected}
                            className="bg-[#3b82f6] text-white px-8 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {bobState.selectedIdInput.trim() ? "OK" : "Skip"}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                {/* Point 5: Bob clarification reply panel — the user's answer input, on
                  the right (user side). The question (with its "Clarify: <file>" title)
                  renders as a Bob bubble above; this is just the input + actions. */}
                {isBobStep &&
                  status === "review_request" &&
                  bobState.clarifyPrompt &&
                  bobState.clarifyData && (
                    <div className="w-[85%] max-w-4xl self-end">
                      <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-br-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-3">
                        <textarea
                          rows={3}
                          value={bobState.clarifyInput}
                          onChange={(e) =>
                            setBobState((prev) => ({
                              ...prev,
                              clarifyInput: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                              e.preventDefault();
                              if (bobState.clarifyInput.trim() && isConnected)
                                handleBobClarifyAnswer(
                                  "clarify_answer",
                                  bobState.clarifyInput,
                                );
                            }
                          }}
                          placeholder="Type the missing details here..."
                          className="rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent resize-y"
                        />
                        <div className="flex flex-wrap gap-3 justify-end">
                          <button
                            onClick={() =>
                              handleBobClarifyAnswer(
                                "clarify_answer",
                                bobState.clarifyInput,
                              )
                            }
                            disabled={!bobState.clarifyInput.trim() || !isConnected}
                            className="bg-[#3b82f6] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            Submit answer
                          </button>
                          <button
                            onClick={() => handleBobClarifyAnswer("skip_file", "")}
                            disabled={!isConnected}
                            className="border border-[#e2e8f0] text-gray-600 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            Skip this file
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                {/* Mary clarification reply panel — the question renders as a Mary bubble
                  above; this is the answer input + actions, on the right (user side). */}
                {isMaryStep && status === "review_request" && maryState.clarifyPrompt && (
                  <div className="w-[85%] max-w-4xl self-end">
                    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-br-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-3">
                      <textarea
                        rows={3}
                        value={maryState.clarifyInput}
                        onChange={(e) =>
                          setMaryState((prev) => ({
                            ...prev,
                            clarifyInput: e.target.value,
                          }))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            if (maryState.clarifyInput.trim() && isConnected)
                              handleMaryClarifyAnswer(
                                "clarify_answer",
                                maryState.clarifyInput,
                              );
                          }
                        }}
                        placeholder="Answer the question here, or skip it..."
                        className="rounded-md border border-[#e2e8f0] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#22c55e] focus:border-transparent resize-y"
                      />
                      <div className="flex flex-wrap gap-3 justify-end">
                        <button
                          onClick={() =>
                            handleMaryClarifyAnswer("clarify_answer", maryState.clarifyInput)
                          }
                          disabled={!maryState.clarifyInput.trim() || !isConnected}
                          className="bg-[#22c55e] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          Submit answer
                        </button>
                        <button
                          onClick={() => handleMaryClarifyAnswer("skip", "")}
                          disabled={!isConnected}
                          className="border border-[#e2e8f0] text-gray-600 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          Skip this question
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Mary per-item test-case review panel */}
                {isMaryStep &&
                  status === "review_request" &&
                  maryState.testCases &&
                  maryState.testCases.length > 0 && (
                    <div className="w-[85%] max-w-4xl self-start">
                      <div className="text-[11px] font-semibold mb-1 text-[#22c55e]">
                        Mary
                        <MessageTime
                          timestamp={
                            messages.find(
                              (m) => m.metadata?.type === "test_case_review",
                            )?.timestamp
                          }
                          fallbackToNow
                        />
                      </div>
                      <MaryReviewPanel
                        testCases={maryState.testCases}
                        onApprove={handleMaryApprove}
                        onReject={handleMaryReject}
                        disabled={!isConnected}
                      />
                    </div>
                  )}

                {/* Sarah inputs form — collect target URL + Chrome path so the
                  browser-use exploration can drive the real app. */}
                {isSarahStep && sarahState.inputsRequest && (
                  <div className="w-[85%] max-w-4xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#8B5CF6]">
                      Sarah
                      <MessageTime
                        timestamp={
                          messages.find(
                            (m) => m.metadata?.type === "sarah_inputs_request",
                          )?.timestamp
                        }
                        fallbackToNow
                      />
                    </div>
                    <SarahInputsForm
                      request={sarahState.inputsRequest}
                      appRoles={selectedProject?.app_roles ?? []}
                      sessions={sarahState.sessions}
                      onSubmit={handleSarahInputsSubmit}
                      disabled={!isConnected}
                      projectId={selectedProjectId ?? undefined}
                    />
                  </div>
                )}

                {/* Sarah input-selection panel */}
                {isSarahStep &&
                  status === "review_request" &&
                  sarahState.testCases &&
                  sarahState.testCases.length > 0 && (
                    <div className="w-[85%] max-w-4xl self-start">
                      <div className="text-[11px] font-semibold mb-1 text-[#8B5CF6]">
                        Sarah
                        <MessageTime
                          timestamp={
                            messages.find(
                              (m) => m.metadata?.type === "test_case_selection",
                            )?.timestamp
                          }
                          fallbackToNow
                        />
                      </div>
                      <SarahInputSelection
                        testCases={sarahState.testCases}
                        onConfirm={handleSarahConfirm}
                        onSkip={handleSarahSkipToJack}
                        disabled={!isConnected}
                      />
                    </div>
                  )}

                {/* Sarah script-review panel — side-by-side review UX (13.5) */}
                {isSarahStep &&
                  status === "review_request" &&
                  sarahState.scripts &&
                  sarahState.scripts.length > 0 && (
                    <div className="w-[85%] max-w-4xl self-start">
                      <div className="text-[11px] font-semibold mb-1 text-[#8B5CF6]">
                        Sarah
                        <MessageTime
                          timestamp={
                            messages.find(
                              (m) => m.metadata?.type === "script_review",
                            )?.timestamp
                          }
                          fallbackToNow
                        />
                      </div>
                      <SarahScriptReviewPanel
                        scripts={sarahState.scripts}
                        onApprove={handleSarahApprove}
                        onReject={handleSarahReject}
                        onSkip={handleSarahSkip}
                        validationErrors={sarahState.validationErrors}
                        disabled={!isConnected}
                      />
                    </div>
                  )}

                {/* Jack input-selection panel (14.1) */}
                {isJackStep &&
                  status === "review_request" &&
                  jackState.scripts &&
                  jackState.scripts.length > 0 && (
                    <div className="w-[85%] max-w-4xl self-start">
                      <div className="text-[11px] font-semibold mb-1 text-[#F97316]">
                        Jack
                        <MessageTime
                          timestamp={
                            messages.find(
                              (m) => m.metadata?.type === "script_selection",
                            )?.timestamp
                          }
                          fallbackToNow
                        />
                      </div>
                      <JackInputSelection
                        scripts={jackState.scripts}
                        environments={jackState.environments}
                        appRoles={jackState.appRoles}
                        sessions={jackState.sessions}
                        onConfirm={handleJackConfirm}
                        onCaptureSession={() => setSessionsPanelOpen(true)}
                        disabled={!isConnected}
                        running={jackRunStarting}
                      />
                    </div>
                  )}

                {/* Jack execution report + history (14.6) */}
                {isJackStep && jackState.summary && selectedProjectId && (
                  <div className="w-[85%] max-w-4xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#F97316]">
                      Jack
                      <MessageTime
                        timestamp={
                          messages.find(
                            (m) => m.metadata?.type === "execution_summary",
                          )?.timestamp
                        }
                        fallbackToNow
                      />
                    </div>
                    <JackExecutionReport
                      projectId={selectedProjectId}
                      summary={jackState.summary}
                    />
                  </div>
                )}

                {/* Sarah DONE — Proceed to Jack affordance (14.1). */}
                {isSarahStep && (status === "completed" || status === "done") && (
                  <div className="w-[85%] max-w-4xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#8B5CF6]">
                      Sarah
                      <MessageTime
                        timestamp={
                          messages.find(
                            (m) => m.metadata?.type === "script_review",
                          )?.timestamp
                        }
                        fallbackToNow
                      />
                    </div>
                    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                      <p className="text-sm font-medium text-gray-700">
                        Scripts reviewed and saved. Ready to run tests with Jack.
                      </p>
                      <button
                        onClick={() =>
                          sendMessage({
                            type: "navigate",
                            step: 5,
                            direction: "next",
                            agentName: "Jack",
                            sender: "user",
                            content: "Navigate to Jack",
                            messageType: "info",
                          })
                        }
                        disabled={!isConnected}
                        className="self-start bg-[#F97316] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#ea580c] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Proceed to Jack →
                      </button>
                    </div>
                  </div>
                )}

                {/* Mary DONE — Proceed to Sarah affordance.
                  Sarah's step-4 UI is Epic 13; landing there shows the existing empty step. */}
                {isMaryStep && (status === "completed" || status === "done") && (
                  <div className="w-[85%] max-w-4xl self-start">
                    <div className="text-[11px] font-semibold mb-1 text-[#22c55e]">
                      Mary
                      <MessageTime
                        timestamp={
                          messages.find(
                            (m) => m.metadata?.type === "test_case_review",
                          )?.timestamp
                        }
                        fallbackToNow
                      />
                    </div>
                    <div className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm overflow-hidden flex flex-col p-5 gap-4">
                      <p className="text-sm font-medium text-gray-700">
                        All test cases reviewed and saved. Ready to generate scripts with Sarah.
                      </p>
                      <button
                        onClick={() =>
                          sendMessage({
                            type: "navigate",
                            step: 4,
                            direction: "next",
                            agentName: "Sarah",
                            sender: "user",
                            content: "Navigate to Sarah",
                            messageType: "info",
                          })
                        }
                        disabled={!isConnected}
                        className="self-start bg-[#22c55e] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Proceed to Sarah →
                      </button>
                    </div>
                  </div>
                )}

                {/* Empty state intentionally hidden to avoid exposing technical waiting states. */}
                {/* Task 6.2: Bottom sentinel — scrollIntoView(this) is always at the true
                  end of the message list even after async content (markdown, etc.) renders. */}
                <div ref={chatBottomRef} aria-hidden="true" />
              </div>
            </div>
            {/* Point 1: floating jump-to-latest pill — only when a new message arrived
              while the user was scrolled up reading earlier messages. */}
            {!selectedArtifact && hasNewMessage && (
              <button
                type="button"
                onClick={scrollToLatestMessage}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 bg-[#3b82f6] text-white rounded-full px-4 py-1.5 text-xs font-semibold shadow-md hover:bg-[#2563eb] active:scale-95 transition-transform"
              >
                <ArrowDown className="w-3 h-3" />
                New message
              </button>
            )}
          </div>

          {/* Artifact Preview — replaces chat content when an artifact is selected */}
          {selectedArtifact && (
            <ArtifactPreview
              artifact={selectedArtifact}
              onClose={() => setSelectedArtifact(null)}
              onSelfMutation={(type) => handleSelfMutation(selectedArtifact.id, type)}
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
      </main>

      {/* Interactive MFA Prompt Overlay */}
      {mfaRequest && (
        <InteractiveMFAPrompt
          projectId={mfaRequest.projectId}
          sessionId={mfaRequest.sessionId}
          environment={mfaRequest.environment}
          role={mfaRequest.role}
          onClose={() => setMfaRequest(null)}
          onSuccess={() => setMfaRequest(null)}
        />
      )}
    </div>
  );
}

export default App;
