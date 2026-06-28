export function AppVersion({ className }: { className?: string }) {
  const version = typeof __APP_VERSION__ !== "undefined" && __APP_VERSION__ ? __APP_VERSION__ : "unknown";
  const displayVersion = version === "dev" || version === "unknown" ? version : `v${version}`;
  
  return (
    <div
      className={className ?? "text-xs text-slate-500 mr-4 self-center select-none"}
      title="Frontend Version"
      aria-label={`Frontend Version: ${displayVersion}`}
    >
      {displayVersion}
    </div>
  );
}
