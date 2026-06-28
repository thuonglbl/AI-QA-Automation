import React, { useState } from "react";
import type { ModelAssignment, ProviderBenchmark } from "@/types/provider";
import { MessageTime } from "@/components/MessageTime";

interface ModelAssignmentReviewProps {
  provider: string;
  endpoint: string;
  assignments: ModelAssignment[] | null;
  availableModels?: Array<{ id: string; name: string }>;
  unavailableModels?: Array<{ id: string; name: string }>;
  onApprove: (updatedAssignments: Record<string, string>) => void;
  disabled?: boolean;
  disabledReason?: string;
  /** ISO timestamp of Alice's message; rendered as hh:mm:ss beside the "Alice" label. */
  messageTimestamp?: string;
  benchmark?: ProviderBenchmark | null;
}

const AGENT_COLORS: Record<string, string> = {
  Alice: "bg-pink-500",
  Bob: "bg-blue-500",
  Mary: "bg-emerald-500",
  Sarah: "bg-violet-500",
  Jack: "bg-orange-500",
};

/** Override key for an assignment: the explicit `key` (e.g. "sarah_explore") or, for older
 *  payloads, the lowercased display name. Must match the backend agent-config key. */
function assignmentKey(a: ModelAssignment): string {
  return a.key ?? a.agent.toLowerCase();
}

/** Dot color: match on the leading word of the label so "Sarah · Browser explore" still
 *  shows Sarah's violet. */
function agentColor(agent: string): string {
  if (AGENT_COLORS[agent]) return AGENT_COLORS[agent];
  const lead = agent.split(/[\s·]/)[0] ?? "";
  return AGENT_COLORS[lead] ?? "bg-black";
}

export function ModelAssignmentReview({
  provider,
  assignments,
  availableModels = [],
  unavailableModels = [],
  onApprove,
  disabled = false,
  disabledReason,
  messageTimestamp,
  benchmark,
}: ModelAssignmentReviewProps) {
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>(
    {},
  );

  const handleModelChange = (agent: string, model: string) => {
    setSelectedModels((prev) => ({ ...prev, [agent]: model }));
  };

  const handleOk = () => {
    const updatedAssignments: Record<string, string> = {};
    assignments?.forEach((a) => {
      const k = assignmentKey(a);
      updatedAssignments[k] = selectedModels[k] || a.model;
    });
    onApprove(updatedAssignments);
  };

  return (
    <div className="max-w-[90vw] md:max-w-max self-start">
      {/* Alice Message */}
      <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">
        Alice
        <MessageTime timestamp={messageTimestamp} fallbackToNow />
      </div>
      <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed">
        ✅ Connected successfully to <strong>{provider}</strong>!
        <br />
        <br />I assigned appropriate models to each agent, if you find out a
        better model you can change by selecting dropdown list below

        {/* Discovered Model Summary */}
        {availableModels.length > 0 && (
          <div className="mt-2 mb-1 text-xs text-[#64748b]">
            Discovered {availableModels.length} available model
            {availableModels.length !== 1 ? "s" : ""} from <strong>{provider}</strong>
          </div>
        )}

        {/* Benchmark Score */}
        {benchmark && benchmark.accuracy_percent != null && (
          <div className="mt-1 mb-2 text-xs text-[#64748b]">
            Global Benchmark Score: <strong>{benchmark.accuracy_percent}%</strong>
            {benchmark.note && <span className="ml-1">({benchmark.note})</span>}
          </div>
        )}

        {/* Model Table */}
        <table className="w-full border-collapse my-2 text-xs">
          <thead>
            <tr>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">
                Agent
              </th>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">
                Role
              </th>
              <th className="text-left py-1.5 px-2 bg-[#f8fafc] border-b border-[#e2e8f0] font-semibold text-[#64748b]">
                Model
              </th>
            </tr>
          </thead>
          <tbody>
            {assignments?.map((assignment) => (
              <React.Fragment key={assignmentKey(assignment)}>
                <tr>
                  <td className="py-1.5 px-2">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-2 h-2 rounded-full inline-block ${agentColor(assignment.agent)}`}
                      ></span>
                      <span>{assignment.agent}</span>
                    </div>
                  </td>
                  <td className="py-1.5 px-2 text-[#64748b]">
                    {assignment.purpose}
                  </td>
                  <td className="py-1.5 px-2">
                    <select
                      aria-label={`Model for ${assignment.agent}`}
                      value={
                        selectedModels[assignmentKey(assignment)] || assignment.model
                      }
                      onChange={(e) =>
                        handleModelChange(assignmentKey(assignment), e.target.value)
                      }
                      disabled={disabled}
                      className="w-full p-1 border border-[#e2e8f0] rounded text-xs bg-white text-[#0f172a] focus:outline-none focus:ring-1 focus:ring-[#3b82f6]"
                    >
                      {availableModels.length > 0 ? (
                        availableModels.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))
                      ) : unavailableModels.length > 0 ? (
                        unavailableModels.map((m) => (
                          <option key={m.id} value={m.id} disabled>
                            {m.name} (Unavailable)
                          </option>
                        ))
                      ) : (
                        <option value={assignment.model}>
                          {assignment.model}
                        </option>
                      )}
                    </select>
                  </td>
                </tr>
                <tr>
                  <td colSpan={3} className="pt-0 pb-3 px-2 border-b border-[#f1f5f9]">
                    <div className="bg-[#f8fafc] p-2 rounded border border-[#e2e8f0] text-[#64748b]">
                      <span className="font-semibold text-[#475569] mr-1">Rationale:</span>
                      {assignment.rationale}
                    </div>
                  </td>
                </tr>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col items-center justify-center gap-2 mt-3">
        <button
          onClick={handleOk}
          disabled={disabled}
          className="px-8 py-2.5 rounded-full bg-[#22c55e] text-white text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          OK
        </button>
        {disabledReason && disabled && (
          <p className="text-xs text-red-500 font-medium">
            {disabledReason}
          </p>
        )}
      </div>
    </div>
  );
}
