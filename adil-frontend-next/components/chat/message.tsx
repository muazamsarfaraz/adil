"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { sanitizeSchema, rehypeSafeLinks } from "@/lib/sanitize";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`py-3 ${isUser ? "bg-gray-50" : "bg-white"}`}>
      <div className="max-w-3xl mx-auto px-4">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">
          {isUser ? "You" : "AskAdil"}
        </div>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[[rehypeSanitize, sanitizeSchema], rehypeSafeLinks]}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
