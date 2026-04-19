import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ChatMessage } from '../ChatMessage';
import type { AgentMessage } from '@/types/pipeline';

describe('ChatMessage', () => {
  const mockAgentMessage: AgentMessage = {
    id: '1',
    sender: 'agent',
    agentName: 'Alice',
    content: 'Hello, how can I help you?',
    timestamp: '2026-04-16T10:00:00Z',
    messageType: 'text'
  };

  const mockUserMessage: AgentMessage = {
    id: '2',
    sender: 'user',
    content: 'I have a question.',
    timestamp: '2026-04-16T10:01:00Z',
    messageType: 'text'
  };
  
  const mockSystemMessage: AgentMessage = {
    id: '3',
    sender: 'system',
    content: 'System notification',
    timestamp: '2026-04-16T10:02:00Z',
    messageType: 'info'
  };

  it('renders agent message correctly', () => {
    render(<ChatMessage message={mockAgentMessage} />);
    
    // Agent name should be visible
    expect(screen.getByText('Alice')).toBeInTheDocument();
    
    // Content should be visible
    expect(screen.getByText('Hello, how can I help you?')).toBeInTheDocument();
    
    // Verify listitem role
    expect(screen.getByRole('listitem')).toBeInTheDocument();
    
    // Verify agent bubble styling: white background, left-aligned justify-start
    const listItem = screen.getByRole('listitem');
    expect(listItem).toHaveClass('justify-start');
    const bubble = listItem.querySelector('[class*="bg-white"]');
    expect(bubble).toBeInTheDocument();
  });

  it('renders user message correctly', () => {
    render(<ChatMessage message={mockUserMessage} />);
    
    // Content should be visible
    expect(screen.getByText('I have a question.')).toBeInTheDocument();
    
    // User message should not display generic agent name or should display User
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    
    // Verify user bubble styling: right-aligned justify-end, contains User label
    const listItem = screen.getByRole('listitem');
    expect(listItem).toHaveClass('justify-end');
    expect(screen.getByText('User')).toBeInTheDocument();
  });
  
  it('renders system message correctly', () => {
    render(<ChatMessage message={mockSystemMessage} />);
    
    // Content should be visible
    expect(screen.getByText('System notification')).toBeInTheDocument();
    
    // System label should be visible
    expect(screen.getByText('System')).toBeInTheDocument();
    
    // Verify system uses left-aligned layout like agent
    const listItem = screen.getByRole('listitem');
    expect(listItem).toHaveClass('justify-start');
    const bubble = listItem.querySelector('[class*="bg-slate-100"]');
    expect(bubble).toBeInTheDocument();
  });
  
  it('handles invalid timestamp gracefully', () => {
    const invalidMessage: AgentMessage = {
      id: '4',
      sender: 'agent',
      agentName: 'Bob',
      content: 'Test message',
      timestamp: 'invalid-date',
      messageType: 'text'
    };
    
    // Should not throw error
    expect(() => render(<ChatMessage message={invalidMessage} />)).not.toThrow();
    
    // Content should still render
    expect(screen.getByText('Test message')).toBeInTheDocument();
  });
  
  it('handles long contiguous strings with break-all', () => {
    const longJwtMessage: AgentMessage = {
      id: '5',
      sender: 'user',
      content: 'ThisIsAVeryLongContinuousStringIntendedToTestTheBreakAllCssUtilityInTheUserInterfaceWithoutTriggeringSecretScanningAlerts1234567890',
      timestamp: '2026-04-16T10:03:00Z',
      messageType: 'text'
    };
    
    render(<ChatMessage message={longJwtMessage} />);
    
    // Content should render without overflow
    const contentElement = screen.getByText(longJwtMessage.content);
    expect(contentElement).toBeInTheDocument();
    expect(contentElement).toHaveClass('break-all');
  });
});
