import React, { useState } from "react";
import { ThinkingTrace } from "../types/provider";
import { MessageTime } from "@/components/MessageTime";

// Shared style for the Available / Unavailable model chip boxes. A taller cap
// (max-h-60) shows far more of a long model list, and an explicitly-styled
// scrollbar forces a classic, always-visible scrollbar instead of the OS
// auto-hiding overlay (which made it look like the list could not be scrolled).
const modelBoxClass =
  "max-h-60 overflow-y-auto bg-white border border-gray-200 rounded p-2 text-xs " +
  "[scrollbar-width:thin] [&::-webkit-scrollbar]:w-2 " +
  "[&::-webkit-scrollbar-track]:bg-gray-100 [&::-webkit-scrollbar-thumb]:rounded-full " +
  "[&::-webkit-scrollbar-thumb]:bg-gray-400";

interface ThinkingBubbleProps {
  trace: ThinkingTrace | null;
  isCompleted?: boolean;
  title?: string;
  /** ISO timestamp of the backing message; shown as hh:mm:ss next to the title. */
  timestamp?: string;
}

export const ThinkingBubble: React.FC<ThinkingBubbleProps> = ({
  trace,
  isCompleted = false,
  title = "Alice's thought",
  timestamp,
}) => {
  // Always start open, user can collapse manually
  const [isOpen, setIsOpen] = useState(true);

  if (!trace) {
    return null;
  }

  const {
    connection_status,
    available_models,
    bootstrap_model,
    bootstrap_rationale,
    assignments,
    chain_of_thought,
  } = trace;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 my-4 font-mono text-sm text-gray-700 shadow-inner">
      <div
        className="flex justify-between items-center cursor-pointer select-none mb-2"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <span className="text-purple-600 font-bold">{title}</span>
          <MessageTime timestamp={timestamp} fallbackToNow />
          {isCompleted && (
            <span className="bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full">
              Complete
            </span>
          )}
        </div>
        <button className="text-gray-400 hover:text-gray-600 focus:outline-none">
          {isOpen ? "▼" : "▶"}
        </button>
      </div>

      {isOpen && (
        <div className="mt-4 space-y-4 border-t border-gray-200 pt-4">
          {connection_status && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">
                Connection Test
              </h4>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${connection_status === "success" ? "bg-green-500" : "bg-red-500"}`}
                ></span>
                <span>
                  {connection_status === "success" ? "Success" : "Failed"}
                </span>
              </div>
            </div>
          )}

          {available_models && available_models.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1 text-green-700">
                Available Models ({available_models.length})
              </h4>
              <div className={modelBoxClass}>
                {available_models.map((m) => (
                  <span
                    key={m.id}
                    className="inline-block bg-green-50 text-green-800 border border-green-200 rounded px-1.5 py-0.5 m-0.5"
                    title={m.name}
                  >
                    {m.id}
                  </span>
                ))}
              </div>
            </div>
          )}

          {trace.unavailable_models && trace.unavailable_models.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1 text-red-700">
                Unavailable Models ({trace.unavailable_models.length})
              </h4>
              <div className={modelBoxClass}>
                {trace.unavailable_models.map((m: any) => (
                  <span
                    key={m.id}
                    className="inline-block bg-red-50 text-red-800 border border-red-200 rounded px-1.5 py-0.5 m-0.5"
                    title={`${m.name} - ${m.status}`}
                  >
                    {m.id} ({m.status})
                  </span>
                ))}
              </div>
            </div>
          )}

          {bootstrap_model && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">
                Alice Bootstrap
              </h4>
              <p className="text-xs">
                Selected model:{" "}
                <span className="font-semibold bg-purple-100 text-purple-800 px-1 rounded">
                  {bootstrap_model}
                </span>
              </p>
              {bootstrap_rationale && (
                <p className="text-xs text-gray-600 mt-1 italic">
                  {bootstrap_rationale}
                </p>
              )}
            </div>
          )}

          {assignments && assignments.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">
                Agent Assignments
              </h4>
              <div className="space-y-2">
                {assignments.map((a, i) => (
                  <div
                    key={i}
                    className="bg-white border border-gray-200 rounded p-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-blue-600 capitalize">
                        {a.agent}
                      </span>
                      {a.tier_source && (
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                            a.tier_source === "admin"
                              ? "bg-purple-100 text-purple-800"
                              : a.tier_source === "curated"
                                ? "bg-green-100 text-green-800"
                                : a.tier_source === "parsed"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-gray-100 text-gray-700"
                          }`}
                          title="How this model was selected"
                        >
                          {a.tier_source}
                        </span>
                      )}
                    </div>
                    <div className="mt-1">
                      <span className="font-semibold">Model:</span> {a.model}
                    </div>
                    <div className="mt-1 text-gray-600 italic">
                      {a.rationale}
                    </div>
                    {a.score_breakdown && (
                      <div className="mt-1 text-gray-400 font-mono text-[10px]">
                        {a.score_breakdown}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {chain_of_thought && chain_of_thought.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">
                Process Status
              </h4>
              <div className="space-y-1 bg-white border border-gray-200 rounded p-2 text-xs">
                {chain_of_thought.map((step, index) => (
                  <div key={index} className="flex gap-2">
                    <span className="text-gray-400">[{index + 1}]</span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
