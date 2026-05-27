import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ExternalLink, Check, X } from 'lucide-react';

interface ExtractedPage {
  page_id: string;
  page_title: string;
  source_url: string;
  raw_html: string;
  requirement_md: string;
}

interface SplitPanelProps {
  pages: ExtractedPage[];
  currentIndex: number;
  totalPages: number;
  onApprove: (pageId: string, updatedMarkdown: string) => void;
  onSkip: (pageId: string) => void;
  disabled?: boolean;
  className?: string;
}

export function SplitPanel({
  pages,
  currentIndex,
  totalPages,
  onApprove,
  onSkip,
  disabled,
  className
}: SplitPanelProps) {
  const page = pages[currentIndex];
  const [markdownContent, setMarkdownContent] = useState('');

  // Reset local state when page changes
  useEffect(() => {
    if (page) {
      setMarkdownContent(page.requirement_md);
    }
  }, [page]);

  if (!page) {
    return <div className="p-4 text-center text-slate-500">No page selected.</div>;
  }

  return (
    <div className={cn("flex flex-col h-[700px] border rounded-md overflow-hidden bg-white shadow-sm", className)}>
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-slate-50">
        <div className="font-medium text-sm text-slate-700">
          Review Requirement Page ({currentIndex + 1} of {totalPages}) — <span className="font-semibold">{page.page_title}</span>
        </div>
        <div className="flex items-center gap-2">
          <a href={page.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
            Open Original <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
      
      {/* Split layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Side: Source HTML */}
        <div className="w-1/2 border-r flex flex-col bg-slate-50">
          <div className="py-2 px-3 border-b text-xs font-medium text-slate-500 uppercase tracking-wider flex justify-between items-center bg-slate-100">
            <span>Raw Source (Read-only)</span>
          </div>
          <div className="flex-1 overflow-hidden bg-white">
            <iframe 
              srcDoc={page.raw_html} 
              className="w-full h-full border-none"
              sandbox="" 
              title={`Source HTML for ${page.page_title}`}
            />
          </div>
        </div>
        
        {/* Right Side: Editable Markdown */}
        <div className="w-1/2 flex flex-col bg-white">
          <div className="py-2 px-3 border-b text-xs font-medium text-slate-500 uppercase tracking-wider bg-slate-100">
            Requirement Markdown (Editable)
          </div>
          <div className="flex-1 p-0 flex">
            <textarea
              className="w-full h-full p-4 resize-none border-none focus:outline-none focus:ring-0 font-mono text-sm text-slate-800 bg-slate-50"
              value={markdownContent}
              onChange={(e) => setMarkdownContent(e.target.value)}
              disabled={disabled}
            />
          </div>
        </div>
      </div>

      {/* Footer Buttons */}
      <div className="flex items-center justify-end gap-3 px-4 py-3 bg-slate-50 border-t">
        <Button 
          variant="outline" 
          onClick={() => onSkip(page.page_id)}
          disabled={disabled}
          className="text-slate-600"
        >
          <X className="w-4 h-4 mr-2" />
          Not requirement
        </Button>
        <Button 
          variant="default" 
          onClick={() => onApprove(page.page_id, markdownContent)}
          disabled={disabled}
          className="bg-blue-600 hover:bg-blue-700"
        >
          <Check className="w-4 h-4 mr-2" />
          Approved
        </Button>
      </div>
    </div>
  );
}
