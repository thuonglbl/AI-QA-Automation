import { useEffect, useState, useMemo, useRef } from "react";
import {
  FolderOpen,
  FolderClosed,
  Plus,
  MessageSquare,
  FileText,
  CheckSquare,
  Code,
  BarChart2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  File,
  MessageCircle,
  Archive,
  Pencil,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { updateThread } from "@/lib/threads";
import { fetchArtifactTree } from "@/lib/artifacts";
import type { ArtifactTreeFolder } from "@/lib/artifacts";

export interface Project {
  id: string;
  name: string;
}

export interface Thread {
  id: string;
  project_id: string | null;
  current_step: number;
  status: string;
  title?: string | null;
  is_archived?: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface Artifact {
  id: string;
  project_id: string;
  kind: string;
  name: string;
  created_at: string;
  updated_at: string;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  thread_id?: string | null;
  /** Resolved creator display name (from /artifacts/tree endpoint). */
  created_by_display?: string | null;
  /** Resolved updater display name (from /artifacts/tree endpoint). */
  updated_by_display?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  warnings?: Array<Record<string, unknown>> | null;
  /** Human-friendly title (e.g. Confluence/Jira page title) shown instead of the id-based name. */
  title?: string | null;
  /** Source id of the parent page, for rendering a Confluence-like requirements tree. */
  parent_source_id?: string | null;
  /** Full ancestor chain from Confluence (root to immediate parent). */
  ancestor_source_ids?: string[] | null;
}

/** Last path segment of an artifact name (e.g. "1234/requirement.md" -> "requirement.md"). */
function lastSegment(name: string): string {
  const parts = name.split("/");
  return parts[parts.length - 1] || name;
}

/** A requirement "result" is a markdown file; everything else is a raw companion. */
export function isMarkdown(a: Artifact): boolean {
  return a.name.toLowerCase().endsWith(".md");
}

/** This artifact's own source page id (the segment before the first "/"). */
function pageIdOf(a: Artifact): string {
  return a.name.split("/")[0] || a.name;
}

/**
 * Normalized page id used as the tree key — strips a trailing ".md" so a flat
 * pre-approval draft "{id}.md" collapses onto its approved "{id}/requirement.md"
 * sibling instead of rendering as a second orphan row.
 */
function treeKey(a: Artifact): string {
  return pageIdOf(a).replace(/\.[^.]+$/, "");
}

/**
 * Friendly label: the persisted title when present. With no title, a title-less
 * REQUIREMENT result ("{id}/requirement.md") falls back to its page id (a unique
 * disambiguator for legacy rows that predate titles); everything else — test cases
 * ("{role}/{slug}.md"), scripts, drafts, raw companions — falls back to the name's
 * last segment. The page-id fallback MUST stay scoped to requirements: a test case's
 * first path segment is its shared role folder, so using it would label every case in
 * a role identically (e.g. all "Attributor").
 */
export function displayLabel(a: Artifact): string {
  const t = a.title?.trim();
  if (t) return t;
  if (a.kind === "requirements" && isMarkdown(a) && a.name.includes("/")) return pageIdOf(a);
  return lastSegment(a.name);
}

export interface TreeRow {
  artifact: Artifact;
  depth: number;
}

/**
 * Prefer the approved (slash-qualified) and/or titled artifact when two results
 * collapse onto the same tree key (e.g. a leftover draft vs its approved copy).
 */
function preferResult(candidate: Artifact, current: Artifact): boolean {
  const candSlash = candidate.name.includes("/");
  const curSlash = current.name.includes("/");
  if (candSlash !== curSlash) return candSlash;
  const candTitle = !!candidate.title?.trim();
  const curTitle = !!current.title?.trim();
  if (candTitle !== curTitle) return candTitle;
  return false;
}

/**
 * Flatten requirement result artifacts into a depth-annotated, pre-order list
 * forming a Confluence-like tree: a node's children are results whose
 * `parent_source_id` equals its page id; roots are results with no resolvable
 * parent in the set. Drafts that share a page with their approved copy are
 * de-duplicated (the approved/titled one wins). Cycle- and orphan-safe (any
 * unvisited result is appended as a root). Stable order by friendly label.
 */
export function buildResultTree(results: Artifact[], allEntries: Artifact[] = []): TreeRow[] {
  // De-duplicate by normalized page id so a leftover "{id}.md" draft never shows
  // as a second row next to its approved "{id}/requirement.md".
  const byKey = new Map<string, Artifact>();
  for (const a of results) {
    const key = treeKey(a);
    const cur = byKey.get(key);
    if (!cur || preferResult(a, cur)) byKey.set(key, a);
  }
  const deduped = [...byKey.values()];

  // Build a map of all entries to resolve missing ancestors
  const allByKey = new Map<string, Artifact>();
  for (const a of allEntries) {
    const key = treeKey(a);
    const cur = allByKey.get(key);
    if (!cur) {
      allByKey.set(key, a);
    } else {
      const candIsMd = isMarkdown(a);
      const curIsMd = isMarkdown(cur);
      if (candIsMd !== curIsMd) {
        if (candIsMd) allByKey.set(key, a);
      } else {
        if (preferResult(a, cur)) allByKey.set(key, a);
      }
    }
  }

  const treeNodes = new Map<string, Artifact>();
  for (const a of deduped) {
    treeNodes.set(treeKey(a), a);
    if (a.ancestor_source_ids) {
      for (const anc of a.ancestor_source_ids) {
        const cleanAnc = anc.trim();
        if (!treeNodes.has(cleanAnc)) {
          const ancArtifact = allByKey.get(cleanAnc);
          if (ancArtifact) {
            treeNodes.set(cleanAnc, ancArtifact);
          }
        }
      }
    }
  }
  const nodesList = [...treeNodes.values()];

  const childrenByParent = new Map<string, Artifact[]>();
  const roots: Artifact[] = [];
  for (const a of nodesList) {
    // Find the closest known ancestor in the tree. Walk the ancestor chain backwards.
    let bestParent = "";
    if (a.ancestor_source_ids && a.ancestor_source_ids.length > 0) {
      for (let i = a.ancestor_source_ids.length - 1; i >= 0; i--) {
        const anc = a.ancestor_source_ids[i]?.trim();
        if (anc && treeNodes.has(anc) && anc !== treeKey(a)) {
          bestParent = anc;
          break;
        }
      }
    }

    // Fall back to immediate parent_source_id if ancestor search yielded nothing
    if (!bestParent) {
      const parent = a.parent_source_id?.trim() || "";
      if (parent && treeNodes.has(parent) && parent !== treeKey(a)) {
        bestParent = parent;
      }
    }

    if (bestParent) {
      const arr = childrenByParent.get(bestParent) ?? [];
      arr.push(a);
      childrenByParent.set(bestParent, arr);
    } else {
      roots.push(a);
    }
  }
  const byLabel = (x: Artifact, y: Artifact) => displayLabel(x).localeCompare(displayLabel(y));
  const rows: TreeRow[] = [];
  const visited = new Set<string>();
  const walk = (a: Artifact, depth: number) => {
    const key = treeKey(a);
    if (visited.has(key)) return; // cycle guard
    visited.add(key);
    rows.push({ artifact: a, depth });
    for (const kid of (childrenByParent.get(key) ?? []).slice().sort(byLabel)) {
      walk(kid, depth + 1);
    }
  };
  for (const root of roots.slice().sort(byLabel)) walk(root, 0);
  for (const a of nodesList) {
    if (!visited.has(treeKey(a))) rows.push({ artifact: a, depth: 0 });
  }
  return rows;
}

interface ProjectSidebarProps {
  currentThreadId: string | null;
  /** Project bound to the active thread, resolved by App (available on cold load). */
  activeProjectId?: string | null;
  onSelectThread: (threadId: string, projectId?: string) => void;
  onNewConversationInProject: (projectId: string) => void;
  artifactRefreshTrigger?: number;
  onSelectArtifact?: (artifact: Artifact | null) => void;
}

// Task 4.3: Re-keyed to backend folder names while keeping frozen labels.
// The backend tree returns: requirements, test_cases, test_scripts, reports.
// The old keys were: requirements, testcase, testscript, report.
type SubFolderType = "conversations" | "requirements" | "test_cases" | "test_scripts" | "reports";

const FOLDER_CONFIG: Record<SubFolderType, { label: string; icon: React.ElementType; emptyMessage: string }> = {
  conversations: { label: "Conversations", icon: MessageSquare, emptyMessage: "Start a new thread to get started." },
  requirements: { label: "Requirements", icon: FileText, emptyMessage: "Talk to Bob to extract requirements." },
  test_cases: { label: "Test Cases", icon: CheckSquare, emptyMessage: "Talk to Mary to generate test cases." },
  test_scripts: { label: "Scripts", icon: Code, emptyMessage: "Talk to Sarah to write test scripts." },
  reports: { label: "Reports", icon: BarChart2, emptyMessage: "Talk to Jack to generate execution reports." },
};

function SubFolder<T>({
  type,
  items,
  renderItem,
  isOpen,
  onToggle,
  action,
}: {
  type: SubFolderType;
  items: T[];
  renderItem: (item: T) => React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
  action?: { icon: React.ElementType; title: string; onClick: (e: React.MouseEvent) => void; testid?: string };
}) {
  const [page, setPage] = useState(1);
  const itemsPerPage = 5;
  const totalPages = Math.ceil(items.length / itemsPerPage);

  useEffect(() => {
    setPage(1);
  }, [items.length]);

  const displayedItems = useMemo(() => {
    const start = (page - 1) * itemsPerPage;
    return items.slice(start, start + itemsPerPage);
  }, [items, page]);
  const { label, icon: Icon, emptyMessage } = FOLDER_CONFIG[type];

  return (
    <div className="mb-1">
      <div className="group/folder flex items-center gap-2 w-full">
        <button
          type="button"
          onClick={onToggle}
          className="flex items-center gap-2 flex-1 text-left px-2 py-1.5 text-xs font-medium text-[#9ca3af] hover:text-white transition-colors cursor-pointer"
        >
          {isOpen ? <FolderOpen size={14} /> : <FolderClosed size={14} />}
          <Icon size={14} />
          <span className="flex-1">{label}</span>
          <span className="text-[10px] bg-[#374151] px-1.5 rounded-full">{items.length}</span>
        </button>

        {action && (
          <button
            type="button"
            className="opacity-0 group-hover/folder:opacity-100 p-1 hover:bg-[#4b5563] rounded-md transition-all text-[#9ca3af] hover:text-white"
            title={action.title}
            data-testid={action.testid}
            onClick={action.onClick}
          >
            <action.icon size={14} />
          </button>
        )}
      </div>

      {isOpen && (
        <div className="pl-6 pr-2 py-1 space-y-1">
          {items.length === 0 ? (
            <div className="text-[11px] text-[#9ca3af] py-1 italic leading-relaxed">{emptyMessage}</div>
          ) : (
            <>
              {displayedItems.map(renderItem)}

              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-1 pb-2">
                  <button
                    type="button"
                    disabled={page === 1}
                    onClick={() => setPage((p) => p - 1)}
                    title="Previous page"
                    aria-label="Previous page"
                    className="p-1 text-[#9ca3af] hover:text-white disabled:opacity-30 disabled:hover:text-[#9ca3af]"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-[10px] text-[#6b7280]">
                    {page} / {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={page === totalPages}
                    onClick={() => setPage((p) => p + 1)}
                    title="Next page"
                    aria-label="Next page"
                    className="p-1 text-[#9ca3af] hover:text-white disabled:opacity-30 disabled:hover:text-[#9ca3af]"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ThreadRow({
  thread,
  isActive,
  onSelect,
  onArchive,
  onRename,
}: {
  thread: Thread;
  isActive: boolean;
  onSelect: () => void;
  onArchive: () => void;
  onRename: (title: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(thread.title ?? "");

  const date = new Date(thread.updated_at || thread.created_at);
  const timeString = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
  }).format(date);

  const label = thread.title ?? `Step ${thread.current_step} - ${thread.status}`;

  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const startRename = () => {
    setEditValue(thread.title ?? "");
    setMenuOpen(false);
    setIsEditing(true);
  };

  const commitRename = () => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== thread.title) {
      onRename(trimmed);
    }
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <div className="px-2 py-1">
        <input
          autoFocus
          aria-label="Rename Conversation"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            else if (e.key === "Escape") setIsEditing(false);
          }}
          className="w-full px-1.5 py-1 text-[11px] rounded bg-[#1f2937] text-white border border-[#3b82f6] outline-none"
        />
      </div>
    );
  }

  return (
    <div className="relative group/thread">
      <button
        data-testid={`thread-${thread.id}`}
        onClick={onSelect}
        onContextMenu={(e) => {
          e.preventDefault();
          setMenuOpen(true);
        }}
        className={`w-full flex items-center justify-between px-2 py-1.5 rounded-md text-[11px] transition-colors ${
          isActive ? "bg-[#374151] text-white" : "text-[#d1d5db] hover:bg-[#374151] hover:text-white"
        }`}
        title={label}
      >
        <div className="flex items-center gap-1.5 overflow-hidden">
          <MessageCircle size={12} className="flex-shrink-0" />
          <span className="truncate">{label}</span>
        </div>
        <span className="text-[10px] text-[#6b7280] flex-shrink-0 ml-1 group-hover/thread:opacity-0 transition-opacity">
          {timeString}
        </span>
      </button>

      <button
        type="button"
        aria-label="Archive Conversation"
        title="Archive Conversation"
        onClick={(e) => {
          e.stopPropagation();
          onArchive();
        }}
        className="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-0 group-hover/thread:opacity-100 p-1 rounded hover:bg-[#4b5563] text-[#9ca3af] hover:text-white transition-all"
      >
        <Archive size={12} />
      </button>

      {menuOpen && (
        <div
          className="absolute right-2 top-full z-50 mt-0.5 min-w-[130px] rounded-md bg-[#1f2937] border border-[#374151] py-1 shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={startRename}
            className="flex items-center gap-2 w-full px-3 py-1.5 text-[11px] text-[#d1d5db] hover:bg-[#374151] hover:text-white text-left"
          >
            <Pencil size={12} /> Rename
          </button>
        </div>
      )}
    </div>
  );
}

export function ProjectSidebar({
  currentThreadId,
  activeProjectId,
  onSelectThread,
  onNewConversationInProject,
  artifactRefreshTrigger,
  onSelectArtifact,
}: ProjectSidebarProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);

  const [threads, setThreads] = useState<Thread[]>([]);
  // Task 4.2: artifact folders from the tree endpoint (replaces flat artifacts list)
  const [artifactFolders, setArtifactFolders] = useState<ArtifactTreeFolder[]>([]);
  const [isLoadingProjectData, setIsLoadingProjectData] = useState(false);

  const [openFolders, setOpenFolders] = useState<Record<SubFolderType, boolean>>({
    conversations: true,
    requirements: true,
    test_cases: true,
    test_scripts: true,
    reports: true,
  });

  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);

  // Per-node collapse state for the Confluence-like requirements tree (by artifact id).
  // Empty = all expanded (default), matching how Confluence shows an opened parent.
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set());
  const toggleNode = (id: string) =>
    setCollapsedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Task 4.5 (D2): track whether we've auto-opened for the current thread
  // to implement the non-sticky one-shot auto-open behavior.
  const autoOpenedForThreadRef = useRef<string | null>(null);

  useEffect(() => {
    async function fetchProjects() {
      try {
        const data = await apiFetch<Project[]>("/projects");
        setProjects(data);
        if (data.length === 1 && data[0]) {
          setOpenProjectId(data[0].id);
        }
      } catch (err) {
        console.error("Failed to fetch projects", err);
      }
    }
    fetchProjects();
  }, []);

  // Task 4.5 (D2): Non-sticky auto-open — when a thread is active and bound to a project,
  // auto-open THAT project in the sidebar (only if nothing is currently open, i.e. one-shot
  // on thread change). A manual click on another project is not reverted.
  //
  // Review P1 fix: derive the bound project from App's `activeProjectId` (resolved from App's
  // own /threads fetch, available on cold reload) instead of the sidebar's local `threads`
  // state — which is empty until a project is opened, so the previous version never auto-opened
  // for multi-project users on reload. Burn the one-shot ref only once the bound project is
  // known, so the cold-load retry (when activeProjectId resolves) is not blocked.
  useEffect(() => {
    if (!currentThreadId) return;
    // Only fire once per thread change
    if (autoOpenedForThreadRef.current === currentThreadId) return;
    // Wait until App resolves the bound project (null on the very first render).
    if (!activeProjectId) return;
    autoOpenedForThreadRef.current = currentThreadId;

    if (openProjectId === null) {
      setOpenProjectId(activeProjectId);
    }
  }, [currentThreadId, activeProjectId, openProjectId]);

  // Task 4.2: Replace flat /artifacts fetch with /artifacts/tree fetch.
  // Keep artifactRefreshTrigger in dependency array (frozen contract — 10-7/10-8).
  useEffect(() => {
    if (!openProjectId) return;

    let isMounted = true;
    async function fetchProjectData() {
      setIsLoadingProjectData(true);
      try {
        const [threadsData, treeData] = await Promise.all([
          apiFetch<Thread[]>("/threads"),
          fetchArtifactTree(openProjectId!),
        ]);

        if (isMounted) {
          setThreads(threadsData.filter((t) => t.project_id === openProjectId));
          setArtifactFolders(treeData.folders);
          setOpenFolders({
            conversations: true,
            requirements: true,
            test_cases: true,
            test_scripts: true,
            reports: true,
          });
        }
      } catch (err) {
        console.error("Failed to fetch project data", err);
      } finally {
        if (isMounted) {
          setIsLoadingProjectData(false);
        }
      }
    }

    fetchProjectData();
    return () => {
      isMounted = false;
    };
  }, [openProjectId, artifactRefreshTrigger]);

  useEffect(() => {
    if (currentThreadId && openProjectId) {
      const exists = threads.some((t) => t.id === currentThreadId);
      if (!exists) {
        apiFetch<Thread[]>("/threads")
          .then((data) => {
            setThreads(data.filter((t) => t.project_id === openProjectId));
          })
          .catch((err) => console.error("Failed to refetch threads", err));
      }
    }
  }, [currentThreadId, openProjectId, threads]);

  const toggleFolder = (type: SubFolderType) => {
    setOpenFolders((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const handleProjectClick = (projectId: string) => {
    if (openProjectId === projectId) {
      setOpenProjectId(null);
    } else {
      setOpenProjectId(projectId);
    }
  };

  const handleArchiveThread = async (threadId: string) => {
    try {
      await updateThread(threadId, { is_archived: true });
      setThreads((prev) => prev.filter((t) => t.id !== threadId));
    } catch (err) {
      console.error("Failed to archive thread", err);
    }
  };

  const handleRenameThread = async (threadId: string, title: string) => {
    try {
      const updated = await updateThread(threadId, { title });
      setThreads((prev) => prev.map((t) => (t.id === threadId ? { ...t, title: updated.title } : t)));
    } catch (err) {
      console.error("Failed to rename thread", err);
    }
  };

  const sortedThreads = useMemo(() => {
    return [...threads].sort((a, b) => {
      const dA = new Date(a.updated_at || a.created_at).getTime();
      const dB = new Date(b.updated_at || b.created_at).getTime();
      return dB - dA;
    });
  }, [threads]);

  // Task 4.3/4.4: Render artifact folders from the tree response.
  // The tree already provides the grouping, empty state and ordering.
  // We map from backend folder name → SubFolderType (which now matches).
  // A single artifact row. `depth` indents it inside the requirements tree.
  // The label is the friendly title (or name basename) as its own standalone
  // text node — the 10-7/10-8 getByText regression guard relies on a lone span.
  const renderArtifactRow = (artifact: Artifact, depth = 0) => {
    const updatedDate = new Date(artifact.updated_at);
    const updatedStr = new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
    }).format(updatedDate);
    const updaterLabel = artifact.updated_by_display
      ? `${updatedStr} · ${artifact.updated_by_display}`
      : updatedStr;

    return (
      <div
        key={artifact.id}
        className={`w-full flex items-start justify-between px-2 py-1.5 rounded-md text-[11px] transition-colors cursor-pointer ${
          selectedArtifactId === artifact.id
            ? "bg-[#3b82f6] text-white"
            : "text-[#d1d5db] hover:bg-[#374151] hover:text-white"
        }`}
        style={depth > 0 ? { marginLeft: depth * 12 } : undefined}
        title={artifact.name}
        onClick={() => {
          setSelectedArtifactId(artifact.id);
          onSelectArtifact?.(selectedArtifactId === artifact.id ? null : artifact);
        }}
      >
        <div className="flex items-start gap-1.5 overflow-hidden flex-1">
          <File size={12} className="flex-shrink-0 mt-0.5" />
          <div className="flex flex-col overflow-hidden">
            {/* Friendly title (or name basename) — standalone text node for 10-7/10-8 getByText. */}
            <span className="truncate">{displayLabel(artifact)}</span>
            <span className="text-[10px] text-[#6b7280] truncate">{updaterLabel}</span>
          </div>
        </div>
      </div>
    );
  };

  // One requirements-tree row, Confluence-style: a parent (has children) shows an
  // expand/collapse chevron; a leaf shows a bullet dot. The chevron toggles the
  // node's subtree; clicking elsewhere on the row opens the artifact.
  const renderTreeNode = (row: { artifact: Artifact; depth: number; hasChildren: boolean }) => {
    const { artifact, depth, hasChildren } = row;
    const isCollapsed = collapsedNodes.has(artifact.id);
    const updatedDate = new Date(artifact.updated_at);
    const updatedStr = new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
    }).format(updatedDate);
    const updaterLabel = artifact.updated_by_display
      ? `${updatedStr} · ${artifact.updated_by_display}`
      : updatedStr;

    return (
      <div
        key={artifact.id}
        className={`w-full flex items-start gap-1 px-2 py-1.5 rounded-md text-[11px] transition-colors cursor-pointer ${
          selectedArtifactId === artifact.id
            ? "bg-[#3b82f6] text-white"
            : "text-[#d1d5db] hover:bg-[#374151] hover:text-white"
        }`}
        style={depth > 0 ? { marginLeft: depth * 12 } : undefined}
        title={artifact.name}
        onClick={() => {
          setSelectedArtifactId(artifact.id);
          onSelectArtifact?.(selectedArtifactId === artifact.id ? null : artifact);
        }}
      >
        {hasChildren ? (
          <button
            type="button"
            aria-label={isCollapsed ? "Expand" : "Collapse"}
            className="flex-shrink-0 mt-0.5 w-3.5 flex justify-center hover:text-white"
            onClick={(e) => {
              e.stopPropagation();
              toggleNode(artifact.id);
            }}
          >
            {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          </button>
        ) : (
          <span
            className="flex-shrink-0 w-3.5 flex justify-center mt-[7px]"
            aria-hidden="true"
          >
            <span className="w-1 h-1 rounded-full bg-current opacity-60" />
          </span>
        )}
        <div className="flex flex-col overflow-hidden flex-1">
          {/* Friendly title — standalone text node for 10-7/10-8 getByText. */}
          <span className="truncate">{displayLabel(artifact)}</span>
          <span className="text-[10px] text-[#6b7280] truncate">{updaterLabel}</span>
        </div>
      </div>
    );
  };

  // Requirements folder: shows ONLY the final result `.md` files, rendered as a
  // Confluence-like tree with friendly names + per-node collapse. Raw extraction
  // companions (html/txt/json/images) are intentionally NOT listed — QA compares
  // each MD against its Confluence source via the link inside the MD. The raw
  // artifacts remain in storage for debugging; they're just hidden from this folder.
  const renderRequirementsFolder = (folder: ArtifactTreeFolder) => {
    const results = folder.entries.filter(isMarkdown);
    const isOpen = openFolders.requirements;
    const { label, icon: Icon, emptyMessage } = FOLDER_CONFIG.requirements;
    const treeRows = buildResultTree(results, folder.entries);

    // Walk the pre-order rows, marking parents (next row is deeper) and hiding the
    // subtree of any collapsed node. (buildResultTree is already cycle-safe.)
    const visibleRows: { artifact: Artifact; depth: number; hasChildren: boolean }[] = [];
    let collapseDepth: number | null = null;
    for (let i = 0; i < treeRows.length; i++) {
      const cur = treeRows[i]!;
      if (collapseDepth !== null) {
        if (cur.depth > collapseDepth) continue; // inside a collapsed subtree
        collapseDepth = null; // exited it
      }
      const next = treeRows[i + 1];
      const hasChildren = !!next && next.depth > cur.depth;
      visibleRows.push({ artifact: cur.artifact, depth: cur.depth, hasChildren });
      if (hasChildren && collapsedNodes.has(cur.artifact.id)) {
        collapseDepth = cur.depth;
      }
    }

    return (
      <div className="mb-1" key="requirements">
        <button
          type="button"
          onClick={() => toggleFolder("requirements")}
          className="flex items-center gap-2 w-full text-left px-2 py-1.5 text-xs font-medium text-[#9ca3af] hover:text-white transition-colors cursor-pointer"
        >
          {isOpen ? <FolderOpen size={14} /> : <FolderClosed size={14} />}
          <Icon size={14} />
          <span className="flex-1">{label}</span>
          <span className="text-[10px] bg-[#374151] px-1.5 rounded-full">{results.length}</span>
        </button>

        {isOpen && (
          <div className="pl-6 pr-2 py-1 space-y-1">
            {results.length === 0 ? (
              <div className="text-[11px] text-[#9ca3af] py-1 italic leading-relaxed">{emptyMessage}</div>
            ) : (
              visibleRows.map(renderTreeNode)
            )}
          </div>
        )}
      </div>
    );
  };

  const renderArtifactFolder = (folder: ArtifactTreeFolder) => {
    const folderType = folder.name as SubFolderType;
    if (!(folderType in FOLDER_CONFIG)) return null;
    if (folder.name === "requirements") return renderRequirementsFolder(folder);

    // Reports is reserved for genuine report artifacts (Bob's domain). Internal
    // "configuration" sidecars — test-case metadata, mary_selected_id.json — are
    // routed here by the storage catch-all but must never surface in the UI, so
    // filter them out (count badge follows the filtered set).
    const items =
      folder.name === "reports"
        ? folder.entries.filter((e) => e.kind !== "configuration")
        : folder.entries;

    return (
      <SubFolder
        key={folder.name}
        type={folderType}
        items={items}
        isOpen={openFolders[folderType]}
        onToggle={() => toggleFolder(folderType)}
        renderItem={(artifact) => renderArtifactRow(artifact)}
      />
    );
  };

  return (
    <div className="flex-1 overflow-y-auto mt-2 select-none pb-4">
      <div className="px-3 py-1 mb-2 text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
        Projects
      </div>
      <div className="space-y-1">
        {projects.map((project) => {
          const isOpen = openProjectId === project.id;

          return (
            <div key={project.id} className="flex flex-col">
              <div
                className={`group flex items-center justify-between px-2 py-1.5 mx-2 rounded-md cursor-pointer transition-colors ${
                  isOpen ? "bg-[#1f2937] text-white" : "text-[#d1d5db] hover:bg-[#374151] hover:text-white"
                }`}
                onClick={() => handleProjectClick(project.id)}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  {isOpen ? (
                    <FolderOpen size={16} className="text-[#3b82f6]" />
                  ) : (
                    <FolderClosed size={16} className="text-[#9ca3af]" />
                  )}
                  <span className="text-sm font-medium truncate">{project.name}</span>
                </div>
              </div>

              {isOpen && (
                <div className="mt-1 mb-2 px-2 border-l border-[#374151] ml-4">
                  {isLoadingProjectData ? (
                    <div className="pl-4 py-2 text-xs text-[#6b7280]">Loading...</div>
                  ) : (
                    <>
                      <SubFolder
                        type="conversations"
                        items={sortedThreads}
                        isOpen={openFolders.conversations}
                        onToggle={() => toggleFolder("conversations")}
                        action={{
                          icon: Plus,
                          title: "New Conversation",
                          testid: `new-thread-${project.id}`,
                          onClick: () => onNewConversationInProject(project.id),
                        }}
                        renderItem={(thread) => (
                          <ThreadRow
                            key={thread.id}
                            thread={thread}
                            isActive={thread.id === currentThreadId}
                            onSelect={() => onSelectThread(thread.id, project.id)}
                            onArchive={() => handleArchiveThread(thread.id)}
                            onRename={(title) => handleRenameThread(thread.id, title)}
                          />
                        )}
                      />

                      {/* Task 4.3/4.2: Render all tree folders from API response.
                          Reports always rendered (even empty) to preserve shipped behavior. */}
                      {artifactFolders.map(renderArtifactFolder)}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
