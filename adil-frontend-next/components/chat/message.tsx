"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MessageProps {
  role: "user" | "assistant";
  content: string;
  onCitationClick?: (index: number) => void;
}

export default function Message({ role, content, onCitationClick }: MessageProps) {
  const isUser = role === "user";

  // Split citation markers [N] into separate text nodes so ReactMarkdown handles the rest
  const parts = content.split(/(\[\d+\])/g);

  function handleCitationClickInner(e: React.MouseEvent) {
    const target = e.target as HTMLElement;
    const citation = target.getAttribute("data-citation");
    if (citation && onCitationClick) {
      onCitationClick(parseInt(citation, 10));
    }
  }

  // Custom components for markdown rendering
  const components: Components = {
    // Style links
    a: ({ children, href, ...props }) => (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:text-brand-700 underline" {...props}>
        {children}
      </a>
    ),
  };

  if (isUser) {
    return (
      <div className="flex gap-3 mb-4">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 bg-gray-200 text-gray-600">
          U
        </div>
        <div className="text-sm text-gray-900 pt-1 font-medium">{content}</div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 mb-6" onClick={handleCitationClickInner}>
      <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 bg-brand-500 text-white">
        A
      </div>
      <div className="text-sm text-gray-700 leading-relaxed prose prose-sm max-w-none prose-headings:text-gray-900 prose-headings:font-semibold prose-h2:text-base prose-h3:text-sm prose-strong:text-gray-800 prose-li:my-0.5 prose-p:my-2 prose-hr:my-4 prose-blockquote:border-brand-300 prose-blockquote:text-gray-600">
        {parts.map((part, i) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (match) {
            return (
              <button
                key={i}
                data-citation={match[1]}
                className="inline-flex items-center justify-center text-brand-500 hover:text-brand-700 font-semibold text-xs mx-0.5 hover:bg-brand-50 rounded px-0.5 transition-colors"
              >
                [{match[1]}]
              </button>
            );
          }
          return (
            <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={components}>
              {part}
            </ReactMarkdown>
          );
        })}
      </div>
    </div>
  );
}
