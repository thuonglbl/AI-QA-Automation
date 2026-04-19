import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ProcessingIndicator } from '../ProcessingIndicator';

describe('ProcessingIndicator', () => {
  it('renders 3 animated dots', () => {
    render(<ProcessingIndicator message="Loading..." />);

    // Check for 3 dots (spans with rounded-full class)
    const dots = document.querySelectorAll('.rounded-full');
    expect(dots.length).toBe(3);
  });

  it('displays the status message', () => {
    const message = 'Reading page 3 of 5...';
    render(<ProcessingIndicator message={message} />);

    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it('has accessibility attributes', () => {
    render(<ProcessingIndicator message="Processing" />);

    const container = screen.getByRole('status');
    expect(container).toHaveAttribute('aria-live', 'polite');
  });

  it('has screen reader text', () => {
    render(<ProcessingIndicator message="Processing" />);

    // Screen reader text combines "Processing:" with the message
    expect(screen.getByText('Processing: Processing')).toBeInTheDocument();
  });

  it('has animation classes when isActive is true', () => {
    render(<ProcessingIndicator message="Loading" isActive={true} />);

    const dots = document.querySelectorAll('.rounded-full');
    expect(dots[0]).toHaveClass('animate-bounce-dot');
    expect(dots[1]).toHaveClass('animate-bounce-dot-delay-1');
    expect(dots[2]).toHaveClass('animate-bounce-dot-delay-2');
  });

  it('has motion-reduce class for accessibility', () => {
    render(<ProcessingIndicator message="Loading" />);

    const dots = document.querySelectorAll('.rounded-full');
    dots.forEach(dot => {
      expect(dot).toHaveClass('motion-reduce:animate-none');
    });
  });

  it('applies custom className', () => {
    const { container } = render(
      <ProcessingIndicator message="Loading" className="custom-class" />
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('stops animation when isActive is false', () => {
    render(<ProcessingIndicator message="Loading" isActive={false} />);

    const dots = document.querySelectorAll('.rounded-full');
    dots.forEach(dot => {
      expect(dot).not.toHaveClass('animate-bounce-dot');
    });
  });
});
