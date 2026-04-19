import React from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ReviewContent } from './ReviewContent';

interface SplitPanelProps {
  sourceUrl: string;
  markdownContent: string;
  currentPage: number;
  totalPages: number;
  className?: string;
}

export function SplitPanel({
  sourceUrl,
  markdownContent,
  currentPage,
  totalPages,
  className
}: SplitPanelProps) {
  return (
    <div className={cn("flex flex-col h-[500px] border rounded-md overflow-hidden bg-white", className)}>
      {/* Header with pagination */}
      <div className="flex items-center justify-between border-b px-4 py-2 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Reviewing Page {currentPage} of {totalPages}
        </div>
        <div className="flex items-center gap-2">
          {/* We only render indicators for pagination here, actual buttons can be synced with ChatInputArea if needed,
              but AC says 'Next/Previous buttons navigate between pages'. 
              Since Approve/Reject handles progression for Bob, maybe we just show the state. */}
          <span className="text-xs text-slate-500">
            Click "Approve" below to advance.
          </span>
        </div>
      </div>
      
      {/* Split layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Side: Source URL Link/Iframe */}
        <div className="w-1/2 border-r flex flex-col bg-slate-50">
          <div className="py-2 px-3 border-b text-xs font-medium text-slate-500 uppercase tracking-wider flex justify-between items-center bg-slate-100">
            <span>Source Document</span>
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline flex items-center gap-1">
              Open Original <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <div className="flex-1 p-4 flex items-center justify-center text-slate-500 text-sm">
            <div className="text-center">
              <p className="mb-2">Due to Confluence security settings, the page cannot be displayed directly inside this iframe.</p>
              <Button asChild variant="outline">
                <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                  Open in New Tab <ExternalLink className="w-4 h-4 ml-2" />
                </a>
              </Button>
            </div>
          </div>
        </div>
        
        {/* Right Side: Parsed Markdown */}
        <div className="w-1/2 flex flex-col bg-white">
          <div className="py-2 px-3 border-b text-xs font-medium text-slate-500 uppercase tracking-wider bg-slate-100">
            Extracted Content
          </div>
          <ScrollArea className="flex-1 p-4">
            <ReviewContent content={markdownContent} />
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
