import { useEffect, useRef } from 'react';

/**
 * Traps focus within the referenced element.
 * Restores focus to the element that was active before the trap was activated upon unmount or when `active` becomes false.
 */
export function useFocusTrap(active: boolean, onEscape?: () => void) {
  const containerRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;

    // Save current focus
    previousFocusRef.current = document.activeElement as HTMLElement;

    // Focus the container if it's focusable, or its first focusable child
    if (containerRef.current) {
      containerRef.current.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onEscape) {
        onEscape();
        e.stopPropagation();
        e.preventDefault();
        return;
      }

      if (e.key !== 'Tab') return;
      if (!containerRef.current) return;

      const focusableElements = containerRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          lastElement?.focus();
          e.preventDefault();
        }
      } else {
        if (document.activeElement === lastElement) {
          firstElement?.focus();
          e.preventDefault();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      // Restore focus
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
      }
    };
  }, [active, onEscape]);

  return containerRef;
}
