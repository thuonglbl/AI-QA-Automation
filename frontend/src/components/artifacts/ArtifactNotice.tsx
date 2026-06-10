import { useEffect, useState } from "react";
import { Info, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ArtifactNoticeType = "update" | "delete";

interface ArtifactNoticeProps {
  type: ArtifactNoticeType;
  artifactName: string;
  onDismiss: () => void;
  className?: string;
}

const NOTICE_CONFIG: Record<
  ArtifactNoticeType,
  {
    icon: React.ElementType;
    bgColor: string;
    borderColor: string;
    textColor: string;
    message: (name: string) => string;
  }
> = {
  update: {
    icon: Info,
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
    textColor: "text-blue-800",
    message: (name) =>
      `"${name}" has a newer version available. The artifact was updated externally.`,
  },
  delete: {
    icon: AlertTriangle,
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
    textColor: "text-amber-800",
    message: (name) =>
      `"${name}" has been deleted or is no longer available.`,
  },
};

export function ArtifactNotice({
  type,
  artifactName,
  onDismiss,
  className,
}: ArtifactNoticeProps) {
  const [visible, setVisible] = useState(true);
  const config = NOTICE_CONFIG[type];
  const Icon = config.icon;

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onDismiss();
    }, 10_000);

    return () => clearTimeout(timer);
  }, [onDismiss]);

  if (!visible) return null;

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-4 py-3 border rounded-md shadow-sm",
        config.bgColor,
        config.borderColor,
        config.textColor,
        className,
      )}
      role="alert"
    >
      <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <p className="flex-1 text-sm">{config.message(artifactName)}</p>
      <button
        onClick={() => {
          setVisible(false);
          onDismiss();
        }}
        className="flex-shrink-0 p-0.5 hover:opacity-70 transition-opacity"
        aria-label="Dismiss notice"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
