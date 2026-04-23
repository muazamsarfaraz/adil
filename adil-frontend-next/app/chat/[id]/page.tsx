"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useSearchParams } from "next/navigation";
import SearchInput from "@/components/search-input";
import Message from "@/components/chat/message";
import SourcesPanel from "@/components/chat/sources-panel";
import SearchingIndicator from "@/components/chat/searching-indicator";
import { queryV2Stream, logClientError, type StreamEvent } from "@/lib/api";
import type { V2Source, UserTier } from "@/lib/types";
import { useBookCount } from "@/lib/use-book-count";

export default function ChatPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const conversationId = params.id as string;

  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [sources, setSources] = useState<V2Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlightedSource, setHighlightedSource] = useState<number | null>(null);
  const [showMobileSources, setShowMobileSources] = useState(false);
  const [activeBookIds, setActiveBookIds] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const hasStarted = useRef(false);
  const bookCount = useBookCount();

  const runStream = useCallback(async (query: string, bookIds?: string[]) => {
    setLoading(true);
    setStatus("searching");
    setStreamingText("");
    setError(null);

    // Add user message
    setMessages((prev) => [...prev, { role: "user", content: query }]);

    const tier = (localStorage.getItem("user_tier") as UserTier) || "layman";

    try {
      await queryV2Stream(
        {
          query,
          user_tier: tier,
          book_ids: bookIds,
          conversation_id: conversationId,
        },
        (event: StreamEvent) => {
          switch (event.type) {
            case "status":
              setStatus(event.status);
              break;
            case "text":
              setStatus(null);
              setStreamingText((prev) => prev + event.text);
              break;
            case "sources": {
              const mapped: V2Source[] = event.sources.map((s) => {
                const bookId = s.book_id || "";
                const sourceType = s.source_type || "unknown";
                let url: string | null = null;
                if (s.usul_slug) {
                  url = `https://usul.ai/en/texts/${s.usul_slug}`;
                } else if (/^\d+$/.test(bookId)) {
                  url = `https://shamela.ws/book/${bookId}`;
                } else if (bookId.startsWith("waqfeya_")) {
                  const id = bookId.slice("waqfeya_".length);
                  url = `https://archive.org/details/FP${id}`;
                } else if (bookId.startsWith("prophet_mosque_")) {
                  url = `https://huggingface.co/datasets/ieasybooks-org/prophet-mosque-library`;
                }
                return {
                  book_id: bookId,
                  title: s.title || "",
                  excerpt: s.excerpt || "",
                  source_type: sourceType,
                  author_name: s.author_name || null,
                  author_death_year: s.author_death_year || null,
                  usul_slug: s.usul_slug || null,
                  url,
                };
              });
              setSources((prev) => [...prev, ...mapped]);
              break;
            }
            case "error":
              setError(event.error);
              logClientError({
                event_type: "client_stream_error",
                path: `/chat/${conversationId}`,
                detail: event.error,
                conversation_id: conversationId,
                user_tier: tier,
                query_text: query,
                meta: { source: "stream_event_error", book_ids_count: bookIds?.length ?? 0 },
              });
              break;
          }
        },
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setError(msg);
      logClientError({
        event_type: "client_stream_error",
        path: `/chat/${conversationId}`,
        detail: msg,
        conversation_id: conversationId,
        user_tier: tier,
        query_text: query,
        meta: {
          source: "fetch_exception",
          error_name: err instanceof Error ? err.name : "Unknown",
          book_ids_count: bookIds?.length ?? 0,
        },
      });
    } finally {
      // Finalize: move streaming text into messages
      setStreamingText((current) => {
        if (current) {
          setMessages((prev) => [...prev, { role: "assistant", content: current }]);
        }
        return "";
      });
      setLoading(false);
      setStatus(null);
    }
  }, [conversationId]);

  // On mount: check for query params from homepage redirect
  useEffect(() => {
    if (hasStarted.current) return;
    hasStarted.current = true;

    const query = searchParams.get("q") || sessionStorage.getItem(`chat_query_${conversationId}`) || "";
    if (!query) return;

    const booksParam = searchParams.get("books");
    const bookIds = booksParam ? booksParam.split(",").filter(Boolean) : [];
    if (bookIds.length > 0) setActiveBookIds(bookIds);

    runStream(query, bookIds.length > 0 ? bookIds : undefined);
  }, [conversationId, searchParams, runStream]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  function handleFollowUp(query: string) {
    runStream(query, activeBookIds.length > 0 ? activeBookIds : undefined);
  }

  function clearFilter() {
    setActiveBookIds([]);
  }

  function handleCitationClick(index: number) {
    setHighlightedSource(index);
    const el = document.getElementById(`source-${index}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <div className="flex h-[calc(100vh-53px)]">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.map((msg, i) => (
            <Message
              key={i}
              role={msg.role}
              content={msg.content}
              onCitationClick={msg.role === "assistant" ? handleCitationClick : undefined}
            />
          ))}

          {/* Streaming text — renders as it arrives */}
          {streamingText && (
            <Message role="assistant" content={streamingText} onCitationClick={handleCitationClick} />
          )}

          {/* Loading / searching indicator */}
          {loading && !streamingText && (
            <SearchingIndicator
              status={status}
              bookCount={bookCount}
              filteredCount={activeBookIds.length || undefined}
            />
          )}

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
              <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700 underline">
                Dismiss
              </button>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Mobile sources toggle */}
        {sources.length > 0 && (
          <button
            onClick={() => setShowMobileSources(!showMobileSources)}
            className="lg:hidden mx-6 mb-2 text-xs text-brand-500 hover:text-brand-600"
          >
            {showMobileSources ? "Hide sources" : `Show sources (${sources.length})`}
          </button>
        )}

        {showMobileSources && (
          <div className="lg:hidden border-t border-gray-200 bg-gray-50 max-h-64 overflow-y-auto">
            <SourcesPanel sources={sources} highlightedIndex={highlightedSource} />
          </div>
        )}

        <div className="border-t border-gray-200 bg-white px-6 py-3">
          {activeBookIds.length > 0 && (
            <div className="mb-2 flex items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Scoped to {activeBookIds.length} selected book{activeBookIds.length === 1 ? "" : "s"}
              </span>
              <button
                type="button"
                onClick={clearFilter}
                className="text-gray-500 hover:text-gray-700 underline"
              >
                Search all books
              </button>
            </div>
          )}
          <SearchInput placeholder="Ask a follow-up..." onSubmit={handleFollowUp} loading={loading} />
        </div>
      </div>

      <div className="w-[35%] border-l border-gray-200 bg-gray-50 hidden lg:block">
        <SourcesPanel sources={sources} highlightedIndex={highlightedSource} />
      </div>
    </div>
  );
}
