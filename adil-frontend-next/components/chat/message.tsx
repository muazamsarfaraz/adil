"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { sanitizeSchema, rehypeSafeLinks } from "@/lib/sanitize";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function RoleIndicator({ isUser }: { isUser: boolean }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span
        className="font-ui text-[11px] uppercase"
        style={{
          letterSpacing: "0.22em",
          color: isUser ? "var(--color-ink-faded)" : "var(--color-emerald)",
        }}
      >
        {isUser ? "You ask" : "Adil replies"}
      </span>
      <div
        className="flex-1 h-px"
        style={{
          background: isUser
            ? "linear-gradient(to right, rgba(15,62,41,0.2), transparent)"
            : "linear-gradient(to right, var(--color-gold) 0%, transparent 80%)",
          opacity: isUser ? 0.7 : 0.55,
        }}
      />
      {!isUser && (
        <span
          className="text-[color:var(--color-gold)]"
          aria-hidden
          style={{ fontSize: 11, letterSpacing: "0.1em" }}
        >
          ❃
        </span>
      )}
    </div>
  );
}

export default function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className="py-6 md:py-7">
      <div className="max-w-3xl mx-auto px-6 md:px-4">
        <RoleIndicator isUser={isUser} />
        {isUser ? (
          <p
            className="font-body text-[color:var(--color-ink)] italic"
            style={{ fontSize: 17, lineHeight: 1.6 }}
          >
            <span
              className="text-[color:var(--color-gold)] mr-1"
              style={{ fontFamily: "var(--font-display)", fontSize: "1.4em", verticalAlign: "-0.12em" }}
              aria-hidden
            >
              “
            </span>
            {message.content}
            <span
              className="text-[color:var(--color-gold)] ml-0.5"
              style={{ fontFamily: "var(--font-display)", fontSize: "1.4em", verticalAlign: "-0.12em" }}
              aria-hidden
            >
              ”
            </span>
          </p>
        ) : (
          <div className={`prose-legal ${message.content.trim().length > 80 ? "has-dropcap" : ""}`}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[[rehypeSanitize, sanitizeSchema], rehypeSafeLinks]}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
