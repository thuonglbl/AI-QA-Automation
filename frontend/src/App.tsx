import { useEffect, useState, useCallback } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePipelineState } from "@/hooks/usePipelineState";
import { AgentTopBar } from "@/components/AgentTopBar";
import { StepDots } from "@/components/StepDots";
import { Badge } from "@/components/ui/badge";
import { ProviderSelector } from "@/components/ProviderSelector";
import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
import { ProcessingIndicator } from "@/components/ProcessingIndicator";
import type { ProviderOption, ModelAssignment } from "@/types/provider";
import type { AgentMessage } from "@/types/pipeline";

interface AliceState {
  providerOptions: ProviderOption[] | null;
  onPremDefaults: { server_url: string; api_key: string } | undefined;
  modelAssignments: ModelAssignment[] | null;
  providerName: string;
  providerEndpoint: string;
}

function App() {
  const { isConnected, error, lastMessage, sendMessage } = useWebSocket();
  const {
    agentConfig,
    status,
    currentStep,
    completedSteps,
    updateFromMessage,
  } = usePipelineState();

  const [aliceState, setAliceState] = useState<AliceState>({
    providerOptions: null,
    onPremDefaults: undefined,
    modelAssignments: null,
    providerName: "",
    providerEndpoint: "",
  });

  // Handle WebSocket messages for Alice-specific UI
  const handleAliceMessage = useCallback((message: AgentMessage) => {
    // Provider options from backend
    if (message.metadata?.type === "provider_options") {
      setAliceState((prev) => ({
        ...prev,
        providerOptions: message.metadata?.options as ProviderOption[] || null,
        onPremDefaults: message.metadata?.onPremDefaults as { server_url: string; api_key: string } | undefined,
      }));
    }

    // Model assignments for review
    if (message.metadata?.model_assignments) {
      setAliceState((prev) => ({
        ...prev,
        modelAssignments: message.metadata?.model_assignments as ModelAssignment[],
        providerName: (message.metadata?.configuration as { provider?: { provider_name?: string } })?.provider?.provider_name || "",
        providerEndpoint: (message.metadata?.provider_endpoint as string) || "",
      }));
    }

    // Clear state when processing starts
    if (message.metadata?.state === "processing") {
      setAliceState((prev) => ({
        ...prev,
        modelAssignments: null,
      }));
    }
  }, []);

  // Update pipeline state when new messages arrive
  useEffect(() => {
    if (lastMessage) {
      updateFromMessage(lastMessage);
      handleAliceMessage(lastMessage);
    }
  }, [lastMessage, updateFromMessage, handleAliceMessage]);

  // Handle provider selection
  const handleProviderSelect = useCallback((providerId: string, credentials: Record<string, string>) => {
    // Send provider selection to backend via WebSocket
    sendMessage({
      type: "start",
      step: 1,
      inputData: {
        provider: providerId,
        credentials,
      },
    });
  }, [sendMessage]);

  // Handle approve/reject
  const handleApprove = useCallback(() => {
    sendMessage({
      type: "approve",
      step: 1,
    });
  }, [sendMessage]);

  const handleReject = useCallback(() => {
    sendMessage({
      type: "reject",
      step: 1,
      feedback: "Change provider",
    });
    // Reset to show provider options again
    setAliceState((prev) => ({
      ...prev,
      modelAssignments: null,
    }));
  }, [sendMessage]);

  // Check if we should show Alice-specific UI
  const isAliceStep = currentStep === 1;
  const showProviderSelector = isAliceStep && aliceState.providerOptions && status === "start" && !aliceState.modelAssignments;
  const showModelReview = isAliceStep && aliceState.modelAssignments && status === "review_request";
  const isProcessing = status === "processing";

  return (
    <div className="flex flex-col h-screen bg-surface-50">
      {/* Connection status bar */}
      <div className="flex items-center justify-end gap-2 px-4 py-2 bg-white border-b border-surface-200">
        <span className="text-sm text-surface-600">WebSocket:</span>
        <Badge
          variant={isConnected ? "default" : "destructive"}
          className={isConnected ? "bg-success text-white" : ""}
        >
          {isConnected ? "Connected" : "Disconnected"}
        </Badge>
      </div>

      {/* Error display */}
      {error && (
        <div className="mx-4 mt-4 p-3 rounded-lg bg-error-light text-error border border-error text-sm">
          {error}
        </div>
      )}

      {/* Agent top bar with status */}
      <AgentTopBar agent={agentConfig} status={status} />

      {/* Step progress indicator */}
      <StepDots currentStep={currentStep} completedSteps={completedSteps} />

      {/* Main content area */}
      <div className="flex-1 p-4 overflow-auto">
        {/* Alice Provider Selector */}
        {showProviderSelector && (
          <ProviderSelector
            options={aliceState.providerOptions}
            onPremDefaults={aliceState.onPremDefaults}
            onSelect={handleProviderSelect}
            disabled={!isConnected}
          />
        )}

        {/* Processing Indicator */}
        {isProcessing && isAliceStep && (
          <ProcessingIndicator
            message="Testing connection to AI provider..."
            isActive={true}
          />
        )}

        {/* Model Assignment Review */}
        {showModelReview && (
          <ModelAssignmentReview
            provider={aliceState.providerName}
            endpoint={aliceState.providerEndpoint}
            assignments={aliceState.modelAssignments}
            onApprove={handleApprove}
            onReject={handleReject}
            disabled={!isConnected}
          />
        )}

        {/* Fallback message display */}
        {!showProviderSelector && !showModelReview && lastMessage && (
          <div className="p-4 rounded-lg bg-white border border-surface-200 shadow-sm">
            <div className="text-sm text-surface-500 mb-2">
              From: {lastMessage.sender} •{" "}
              {new Date(lastMessage.timestamp).toLocaleTimeString()}
            </div>
            <div className="text-surface-900">{lastMessage.content}</div>
          </div>
        )}

        {/* Empty state */}
        {!showProviderSelector && !showModelReview && !lastMessage && (
          <div className="h-full flex items-center justify-center text-surface-400">
            <div className="text-center">
              <p className="mb-2">Waiting for messages...</p>
              <p className="text-sm">
                Connect to WebSocket to start the AI QA pipeline
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
