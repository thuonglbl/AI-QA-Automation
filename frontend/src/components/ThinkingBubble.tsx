import React, { useState } from 'react';
import { ThinkingTrace } from '../types/provider';

interface ThinkingBubbleProps {
  trace: ThinkingTrace | null;
  isCompleted?: boolean;
  title?: string;
}

export const ThinkingBubble: React.FC<ThinkingBubbleProps> = ({ trace, isCompleted = false, title = "Alice's thought" }) => {
  // Default to open if not completed, closed if completed
  const [isOpen, setIsOpen] = useState(!isCompleted);

  if (!trace) {
    return null;
  }

  const { connection_status, available_models, bootstrap_model, assignments, chain_of_thought } = trace;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 my-4 font-mono text-sm text-gray-700 shadow-inner">
      <div 
        className="flex justify-between items-center cursor-pointer select-none mb-2"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <span className="text-purple-600 font-bold">{title}</span>
          {isCompleted && (
            <span className="bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full">
              Complete
            </span>
          )}
        </div>
        <button className="text-gray-400 hover:text-gray-600 focus:outline-none">
          {isOpen ? '▼' : '▶'}
        </button>
      </div>

      {isOpen && (
        <div className="mt-4 space-y-4 border-t border-gray-200 pt-4">
          {connection_status && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">Connection Test</h4>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${connection_status === 'success' ? 'bg-green-500' : 'bg-red-500'}`}></span>
                <span>{connection_status === 'success' ? 'Success' : 'Failed'}</span>
              </div>
            </div>
          )}

          {available_models && available_models.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">Discovered Models ({available_models.length})</h4>
              <div className="max-h-24 overflow-y-auto bg-white border border-gray-200 rounded p-2 text-xs">
                {available_models.map((m) => (
                  <span key={m.id} className="inline-block bg-gray-100 rounded px-1.5 py-0.5 m-0.5">
                    {m.id}
                  </span>
                ))}
              </div>
            </div>
          )}

          {bootstrap_model && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">Alice Bootstrap</h4>
              <p className="text-xs">
                Selected heuristic model: <span className="font-semibold bg-purple-100 text-purple-800 px-1 rounded">{bootstrap_model}</span>
              </p>
            </div>
          )}

          {assignments && assignments.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">Agent Assignments</h4>
              <div className="space-y-2">
                {assignments.map((a, i) => (
                  <div key={i} className="bg-white border border-gray-200 rounded p-2 text-xs">
                    <div className="font-semibold text-blue-600 capitalize">{a.agent}</div>
                    <div className="mt-1">
                      <span className="font-semibold">Model:</span> {a.model}
                    </div>
                    <div className="mt-1 text-gray-600 italic">
                      {a.rationale}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {chain_of_thought && chain_of_thought.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">Process Status</h4>
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
