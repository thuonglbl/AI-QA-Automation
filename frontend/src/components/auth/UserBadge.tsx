import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import type { AuthUser } from "@/lib/auth";

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  project_admin: "Project Admin",
  standard: "User",
};

// Highest-privilege first, so the label reads "Admin · Project Admin · User".
const ROLE_ORDER = ["admin", "project_admin", "standard"];

/** The user's effective platform role set (lower-cased), falling back to [role]. */
export function effectiveRoles(user: AuthUser | null | undefined): Set<string> {
  if (!user) return new Set<string>();
  const list =
    user.roles && user.roles.length > 0
      ? user.roles
      : user.role
        ? [user.role]
        : [];
  return new Set(list.map((r) => r.toLowerCase()));
}

/** Human label for the user's role set, e.g. "Admin · Project Admin". */
export function roleSetLabel(user: AuthUser | null | undefined): string {
  const roles = effectiveRoles(user);
  const labels = ROLE_ORDER.filter((r) => roles.has(r)).map(
    (r) => ROLE_LABELS[r] ?? r,
  );
  return labels.join(" · ") || "User";
}

function initialsFor(user: AuthUser | null | undefined): string {
  const source =
    user?.display_name || user?.name || user?.email || "?";
  const parts = source.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

interface UserBadgeProps {
  user: AuthUser | null | undefined;
  /** Accent color (tailwind text-* class) for the role label. */
  roleClassName?: string;
  /** Override the displayed role text instead of computing from the user's role set. */
  displayRole?: string;
}

/**
 * Header identity block (Epic 23, story 23.4): name + role-set label + an Azure
 * avatar with an initials fallback. Reused across the workspace + both dashboards.
 */
export function UserBadge({
  user,
  roleClassName = "text-blue-600",
  displayRole,
}: UserBadgeProps) {
  const name = user?.display_name || user?.name || user?.email || "User";
  return (
    <div className="flex items-center gap-3">
      <div className="hidden md:block text-right">
        <div className="text-sm font-semibold text-slate-900">{name}</div>
        <div className="text-xs text-slate-500">
          {user?.email ? <>{user.email} · </> : null}
          <span className={`${roleClassName} font-medium`}>
            {displayRole || roleSetLabel(user)}
          </span>
        </div>
      </div>
      <Avatar className="h-8 w-8" data-testid="user-avatar">
        {user?.avatarUrl ? (
          <AvatarImage src={user.avatarUrl} alt={name} />
        ) : null}
        <AvatarFallback className="bg-slate-200 text-slate-700 text-xs font-semibold">
          {initialsFor(user)}
        </AvatarFallback>
      </Avatar>
    </div>
  );
}
