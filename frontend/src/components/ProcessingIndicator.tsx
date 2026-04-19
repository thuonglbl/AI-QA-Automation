import type { ProcessingIndicatorProps } from '@/types/pipeline';
import { cn } from '@/lib/utils';

export function ProcessingIndicator({
  message,
  isActive = true,
  className,
}: ProcessingIndicatorProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex items-center gap-3', className)}
    >
      {/* Animated dots */}
      <div className="flex items-center gap-1">
        <span
          className={cn(
            'h-2 w-2 rounded-full bg-slate-400',
            isActive && 'animate-bounce-dot',
            'motion-reduce:animate-none'
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            'h-2 w-2 rounded-full bg-slate-400',
            isActive && 'animate-bounce-dot-delay-1',
            'motion-reduce:animate-none'
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            'h-2 w-2 rounded-full bg-slate-400',
            isActive && 'animate-bounce-dot-delay-2',
            'motion-reduce:animate-none'
          )}
          aria-hidden="true"
        />
      </div>

      {/* Status message */}
      <span className="text-sm text-slate-600">{message}</span>

      {/* Screen reader only text */}
      <span className="sr-only">Processing: {message}</span>
    </div>
  );
}
