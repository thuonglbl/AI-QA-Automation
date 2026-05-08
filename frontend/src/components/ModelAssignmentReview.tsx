import type { ModelAssignment } from "@/types/provider";

interface ModelAssignmentReviewProps {
  provider: string;
  endpoint: string;
  assignments: ModelAssignment[] | null;
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
}

const AGENT_ICONS: Record<string, string> = {
  Bob: "🔵",
  Mary: "🟢",
  Sarah: "🟣",
  Jack: "🟠",
};

export function ModelAssignmentReview({
  provider,
  assignments,
  onApprove,
  onReject,
  disabled = false,
}: ModelAssignmentReviewProps) {
  return (
    <div className="max-w-[600px] self-start">
      {/* Alice Message */}
      <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">Alice</div>
      <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed">
        ✅ Connected successfully to <strong>{provider}</strong>!
        <br /><br />
        Here's how I'll assign models to each agent:

        {/* Model Table */}
        <table className="w-full border-collapse my-2 text-xs">
          <thead>
            <tr>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">Agent</th>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">Role</th>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">Model</th>
            </tr>
          </thead>
          <tbody>
            {assignments?.map((assignment) => (
              <tr key={assignment.agent}>
                <td className="py-1.5 px-2 border-b border-[#f1f5f9]">
                  {AGENT_ICONS[assignment.agent]} {assignment.agent}
                </td>
                <td className="py-1.5 px-2 border-b border-[#f1f5f9] text-[#64748b]">
                  {assignment.purpose}
                </td>
                <td className="py-1.5 px-2 border-b border-[#f1f5f9]">
                  <strong>{assignment.model}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <em className="text-xs text-[#64748b]">
          Bob uses Opus (highest quality) for requirement extraction. Other agents use Sonnet for speed and cost efficiency.
        </em>
        <br /><br />
        Does this look right to you?
      </div>

      {/* Action Buttons */}
      <div className="flex gap-2 mt-3">
        <button
          onClick={onApprove}
          disabled={disabled}
          className="flex-1 px-4 py-2.5 rounded-full bg-[#22c55e] text-white text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          Approve ✓
        </button>
        <button
          onClick={onReject}
          disabled={disabled}
          className="flex-1 px-4 py-2.5 rounded-full bg-white text-[#ef4444] border border-[#fca5a5] text-sm font-medium hover:bg-[#fef2f2] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          Reject ✗
        </button>
      </div>
    </div>
  );
}
