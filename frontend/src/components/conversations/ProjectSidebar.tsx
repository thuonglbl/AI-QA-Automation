import { useEffect, useState, useMemo } from "react";
import { FolderOpen, FolderClosed, Plus, MessageSquare, FileText, CheckSquare, Code, BarChart2, ChevronLeft, ChevronRight, File, MessageCircle, Archive, Pencil } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { updateThread } from "@/lib/threads";

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
}

interface ProjectSidebarProps {
  currentThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onNewConversationInProject: (projectId: string) => void;
  artifactRefreshTrigger?: number;
  onSelectArtifact?: (artifact: Artifact | null) => void;
}

type SubFolderType = 'conversations' | 'requirements' | 'testcase' | 'testscript' | 'report';

const FOLDER_CONFIG: Record<SubFolderType, { label: string; icon: React.ElementType }> = {
  conversations: { label: 'Conversations', icon: MessageSquare },
  requirements: { label: 'Requirements', icon: FileText },
  testcase: { label: 'Test Cases', icon: CheckSquare },
  testscript: { label: 'Scripts', icon: Code },
  report: { label: 'Reports', icon: BarChart2 },
};

function SubFolder<T>({ 
  type, 
  items, 
  renderItem, 
  isOpen, 
  onToggle,
  action 
}: { 
  type: SubFolderType; 
  items: T[]; 
  renderItem: (item: T) => React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
  action?: { icon: React.ElementType, title: string, onClick: (e: React.MouseEvent) => void };
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

  const { label, icon: Icon } = FOLDER_CONFIG[type];

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
            onClick={action.onClick}
          >
            <action.icon size={14} />
          </button>
        )}
      </div>
      
      {isOpen && (
        <div className="pl-6 pr-2 py-1 space-y-1">
          {items.length === 0 ? (
            <div className="text-[11px] text-[#6b7280] py-1 italic">Empty</div>
          ) : (
            <>
              {displayedItems.map(renderItem)}
              
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-1 pb-2">
                  <button 
                    type="button"
                    disabled={page === 1}
                    onClick={() => setPage(p => p - 1)}
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
                    onClick={() => setPage(p => p + 1)}
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
  const timeString = new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric'
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
        <span className="text-[10px] text-[#6b7280] flex-shrink-0 ml-1 group-hover/thread:opacity-0 transition-opacity">{timeString}</span>
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

export function ProjectSidebar({ currentThreadId, onSelectThread, onNewConversationInProject, artifactRefreshTrigger, onSelectArtifact }: ProjectSidebarProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);
  
  const [threads, setThreads] = useState<Thread[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoadingProjectData, setIsLoadingProjectData] = useState(false);
  
  const [openFolders, setOpenFolders] = useState<Record<SubFolderType, boolean>>({
    conversations: true,
    requirements: true,
    testcase: true,
    testscript: true,
    report: true,
  });

  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);

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

  useEffect(() => {
    if (!openProjectId) return;
    
    let isMounted = true;
    async function fetchProjectData() {
      setIsLoadingProjectData(true);
      try {
        const [threadsData, artifactsData] = await Promise.all([
          apiFetch<Thread[]>("/threads"),
          apiFetch<Artifact[]>(`/projects/${openProjectId}/artifacts`)
        ]);
        
        if (isMounted) {
          setThreads(threadsData.filter(t => t.project_id === openProjectId));
          setArtifacts(artifactsData);
          setOpenFolders({
            conversations: true,
            requirements: true,
            testcase: true,
            testscript: true,
            report: true,
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
    return () => { isMounted = false; };
  }, [openProjectId, artifactRefreshTrigger]);

  useEffect(() => {
    if (currentThreadId && openProjectId) {
      const exists = threads.some(t => t.id === currentThreadId);
      if (!exists) {
        apiFetch<Thread[]>("/threads").then(data => {
          setThreads(data.filter(t => t.project_id === openProjectId));
        }).catch(err => console.error("Failed to refetch threads", err));
      }
    }
  }, [currentThreadId, openProjectId, threads]);

  const toggleFolder = (type: SubFolderType) => {
    setOpenFolders(prev => ({ ...prev, [type]: !prev[type] }));
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
      setThreads(prev => prev.filter(t => t.id !== threadId));
    } catch (err) {
      console.error("Failed to archive thread", err);
    }
  };

  const handleRenameThread = async (threadId: string, title: string) => {
    try {
      const updated = await updateThread(threadId, { title });
      setThreads(prev =>
        prev.map(t => (t.id === threadId ? { ...t, title: updated.title } : t)),
      );
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

  const getArtifactsByKind = (kind: string) => {
    return artifacts.filter(a => a.kind === kind).sort((a, b) => {
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  };

  return (
    <div className="flex-1 overflow-y-auto mt-2 select-none pb-4">
      <div className="px-3 py-1 mb-2 text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
        Projects
      </div>
      <div className="space-y-1">
        {projects.map(project => {
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
                  {isOpen ? <FolderOpen size={16} className="text-[#3b82f6]" /> : <FolderClosed size={16} className="text-[#9ca3af]" />}
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
                        onToggle={() => toggleFolder('conversations')}
                        action={{
                          icon: Plus,
                          title: "New Conversation",
                          onClick: () => onNewConversationInProject(project.id)
                        }}
                        renderItem={(thread) => (
                          <ThreadRow
                            key={thread.id}
                            thread={thread}
                            isActive={thread.id === currentThreadId}
                            onSelect={() => onSelectThread(thread.id)}
                            onArchive={() => handleArchiveThread(thread.id)}
                            onRename={(title) => handleRenameThread(thread.id, title)}
                          />
                        )}
                      />
                      
                      {['requirements', 'testcase', 'testscript', 'report'].map((kind) => {
                        const items = getArtifactsByKind(kind);
                        return (
                          <SubFolder
                            key={kind}
                            type={kind as SubFolderType}
                            items={items}
                            isOpen={openFolders[kind as SubFolderType]}
                            onToggle={() => toggleFolder(kind as SubFolderType)}
                            renderItem={(artifact) => (
                              <div
                                key={artifact.id}
                                className={`w-full flex items-center justify-between px-2 py-1.5 rounded-md text-[11px] transition-colors cursor-pointer ${
                                  selectedArtifactId === artifact.id
                                    ? "bg-[#3b82f6] text-white"
                                    : "text-[#d1d5db] hover:bg-[#374151] hover:text-white"
                                }`}
                                title={artifact.name}
                                onClick={() => {
                                  setSelectedArtifactId(artifact.id);
                                  onSelectArtifact?.(selectedArtifactId === artifact.id ? null : artifact);
                                }}
                              >
                                <div className="flex items-center gap-1.5 overflow-hidden">
                                  <File size={12} className="flex-shrink-0" />
                                  <span className="truncate">{artifact.name}</span>
                                </div>
                              </div>
                            )}
                          />
                        );
                      })}
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
