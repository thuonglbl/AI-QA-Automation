import React from 'react';
import { AgentConfig, AgentStatus } from '../types/pipeline';
import { Avatar, AvatarFallback } from './ui/avatar';
import { Badge } from './ui/badge';
import { Loader2, Eye, Check } from 'lucide-react';

interface AgentTopBarProps {
  agent: AgentConfig;
  status: AgentStatus;
}

export function AgentTopBar({ agent, status }: AgentTopBarProps) {
  return (
    <div 
      className="flex items-center justify-between p-4 border-b bg-background"
      role="banner"
    >
      <div className="flex items-center space-x-4">
        <Avatar>
          <AvatarFallback style={{ backgroundColor: agent.color, color: 'white' }}>
            {agent.avatar}
          </AvatarFallback>
        </Avatar>
        <div>
          <h2 className="text-lg font-semibold">{agent.displayName}</h2>
          <p className="text-sm text-muted-foreground">Step {agent.stepNumber} of 5</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <span className="text-sm font-medium">{agent.stepTitle}</span>
        <StatusBadge status={status} />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: AgentStatus }) {
  const isValidStatus = ['start', 'processing', 'review_request', 'done', 'completed'].includes(status);
  
  if (!isValidStatus) {
    return (
      <div aria-live="polite">
        <Badge variant="outline" className="bg-slate-100 text-slate-500 border-slate-200">
          Unknown Status
        </Badge>
      </div>
    );
  }

  return (
    <div aria-live="polite">
      {status === 'start' && (
        <Badge variant="outline" className="bg-white text-slate-600 border-slate-200">
          Start
        </Badge>
      )}
      {status === 'processing' && (
        <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100 animate-pulse transition-opacity duration-150 border-0">
          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
          Processing
        </Badge>
      )}
      {status === 'review_request' && (
        <Badge className="bg-blue-500 text-white hover:bg-blue-600 transition-opacity duration-150">
          <Eye className="w-3 h-3 mr-1" />
          Review Requested
        </Badge>
      )}
      {(status === 'done' || status === 'completed') && (
        <Badge className="bg-green-500 text-white hover:bg-green-600 transition-opacity duration-150">
          <Check className="w-3 h-3 mr-1" />
          {status === 'completed' ? 'Completed' : 'Done'}
        </Badge>
      )}
    </div>
  );
}
