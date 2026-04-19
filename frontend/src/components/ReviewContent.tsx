import React, { CSSProperties } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface ReviewContentProps {
  content: string;
  className?: string;
}

// Type for SyntaxHighlighter style
const syntaxHighlighterStyle: { [key: string]: CSSProperties } = vscDarkPlus;

// Type for code component props
interface CodeComponentProps {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

// Type for table cell props
interface TableCellProps {
  children?: React.ReactNode;
}

export function ReviewContent({ content, className }: ReviewContentProps) {
  const components: Components = {
    code: ({ inline, className: codeClassName, children, ...props }: CodeComponentProps) => {
      const match = /language-(\w+)/.exec(codeClassName || '');
      return !inline && match ? (
        <SyntaxHighlighter
          {...props}
          style={syntaxHighlighterStyle}
          language={match[1]}
          PreTag="div"
          className="rounded-md my-4 text-xs !m-0 !mt-2 !mb-2"
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code {...props} className={cn("bg-slate-100 text-slate-800 px-1 py-0.5 rounded text-xs font-mono break-words", codeClassName)}>
          {children}
        </code>
      );
    },
    table: ({ children }: TableCellProps) => {
      return (
        <div className="overflow-x-auto my-4 border rounded-md border-slate-200">
          <table className="w-full text-sm text-left">
            {children}
          </table>
        </div>
      );
    },
    th: ({ children }: TableCellProps) => {
      return <th className="bg-slate-50 px-3 py-2 font-semibold text-slate-700 border-b">{children}</th>;
    },
    td: ({ children }: TableCellProps) => {
      return <td className="px-3 py-2 border-b border-slate-100">{children}</td>;
    },
  };

  return (
    <ScrollArea className={cn("w-full max-h-[400px]", className)}>
      <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:p-0 my-0 break-words">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={components}
        >
          {content || ''}
        </ReactMarkdown>
      </div>
    </ScrollArea>
  );
}
