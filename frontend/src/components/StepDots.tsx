import React from 'react';

interface StepDotsProps {
  currentStep: number;
  completedSteps: number;
}

export function StepDots({ currentStep, completedSteps }: StepDotsProps) {
  const totalSteps = 5;

  return (
    <div 
      className="flex items-center justify-center space-x-4 py-4 border-b bg-slate-50/50"
      role="progressbar"
      aria-valuenow={currentStep}
      aria-valuemax={totalSteps}
      aria-valuemin={1}
    >
      {Array.from({ length: totalSteps }).map((_, index) => {
        const stepNum = index + 1;
        
        // Per UX-DR6 and UX-DR9:
        let dotClass = 'bg-slate-300'; // pending
        if (stepNum <= completedSteps) {
          dotClass = 'bg-green-500'; // completed
        } else if (stepNum === currentStep) {
          dotClass = 'bg-blue-500'; // active
        }

        return (
          <div key={index} className="flex items-center">
            {/* The dot */}
            <div className={`w-2 h-2 rounded-full ${dotClass} transition-colors duration-300`} />
            
            {/* The line connecting dots */}
            {stepNum < totalSteps && (
              <div 
                className={`w-12 h-0.5 mx-2 ${
                  stepNum < completedSteps || (stepNum === completedSteps && stepNum < currentStep)
                    ? 'bg-green-500' 
                    : 'bg-slate-200'
                } transition-colors duration-300`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
