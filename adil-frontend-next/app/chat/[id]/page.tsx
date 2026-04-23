"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Message, { type ChatMessage } from "@/components/chat/message";
import SourcesPanel from "@/components/chat/sources-panel";
import ViabilityCard from "@/components/chat/viability-card";
import JurisdictionSelector from "@/components/jurisdiction-selector";
import SearchingIndicator from "@/components/searching-indicator";
import ErrorBoundary from "@/components/error-boundary";
import Composer from "@/components/composer";
import ReportFlow from "@/components/report/report-flow";
import type { UploadedImage } from "@/components/image-upload";
import { readJurisdictionClient } from "@/lib/jurisdiction";
import type { Jurisdiction, Source, Viability } from "@/lib/types";
import { streamChat } from "@/lib/stream";
import { queryImage } from "@/lib/api";

export default function ChatPage() {
  const params = useParams<{ id: string }>();
  const conversationId = params?.id ?? "";

  const [jurisdiction, setJurisdiction] = useState<Jurisdiction | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sourcesByMsg, setSourcesByMsg] = useState<Record<number, Source[]>>({});
  const [viabilityByMsg, setViabilityByMsg] = useState<Record<number, Viability>>({});
  const [streaming, setStreaming] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setJurisdiction(readJurisdictionClient());
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  const send = async (text: string, images: UploadedImage[]) => {
    if (!jurisdiction) return;
    if (text.trim().toLowerCase() === "report") {
      setShowReport(true);
      return;
    }

    const userMsg: ChatMessage = { role: "user", content: text };
    const assistantIdx = messages.length + 1;
    setMessages((m) => [...m, userMsg, { role: "assistant", content: "" }]);

    if (images.length > 0) {
      setStreaming(true);
      try {
        const resp = (await queryImage({
          query: text,
          conversation_id: conversationId,
          upload_ids: images.map((i) => i.upload_id) as [string, ...string[]],
        })) as { answer: string; sources?: Source[]; viability_assessment?: Viability };
        setMessages((m) => {
          const copy = [...m];
          copy[assistantIdx] = { role: "assistant", content: resp.answer };
          return copy;
        });
        if (resp.sources) setSourcesByMsg((s) => ({ ...s, [assistantIdx]: resp.sources! }));
        if (resp.viability_assessment)
          setViabilityByMsg((v) => ({ ...v, [assistantIdx]: resp.viability_assessment! }));
      } catch (e) {
        setMessages((m) => {
          const copy = [...m];
          copy[assistantIdx] = { role: "assistant", content: `⚠️ ${e instanceof Error ? e.message : "Upload failed"}` };
          return copy;
        });
      } finally {
        setStreaming(false);
      }
      return;
    }

    setStreaming(true);
    abortRef.current = new AbortController();

    await streamChat({
      url: "/api/chat/stream",
      signal: abortRef.current.signal,
      body: {
        query: text,
        conversation_id: conversationId,
        conversation_history: messages
          .filter((m) => m.content.trim().length > 0)
          .map((m) => ({
            // Backend uses Gemini's {user, model} role convention, not {user, assistant}
            role: m.role === "assistant" ? "model" : "user",
            content: m.content,
          })),
        jurisdiction,
        max_sources: 10,
        include_viability_score: true,
      },
      onEvent: (e) => {
        if (e.event === "token") {
          setMessages((m) => {
            const copy = [...m];
            copy[assistantIdx] = { ...copy[assistantIdx], content: (copy[assistantIdx]?.content ?? "") + e.data };
            return copy;
          });
        } else if (e.event === "source") {
          setSourcesByMsg((s) => ({ ...s, [assistantIdx]: [...(s[assistantIdx] ?? []), e.data] }));
        } else if (e.event === "viability") {
          setViabilityByMsg((v) => ({ ...v, [assistantIdx]: e.data }));
        }
      },
      onError: ({ message, status, retryAfter }) => {
        const hint = status === 429
          ? `Rate limited. Try again in ${retryAfter ?? "a few"} seconds.`
          : message;
        setMessages((m) => {
          const copy = [...m];
          copy[assistantIdx] = { ...copy[assistantIdx], content: `⚠️ ${hint}` };
          return copy;
        });
      },
    });

    setStreaming(false);
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollerRef} className="flex-1 overflow-y-auto">
        <ErrorBoundary>
          <div className="max-w-3xl mx-auto px-4 py-6">
            {messages.length === 0 && !jurisdiction && (
              <div className="bg-white p-4 rounded border border-gray-200">
                <p className="text-sm">
                  Welcome to AskAdil — free AI legal education for British Muslims.
                  We cover UK discrimination, hate crime, and mental capacity / Court of Protection.
                  Please select your jurisdiction to begin:
                </p>
                <JurisdictionSelector onSelect={setJurisdiction} />
              </div>
            )}
            {messages.length === 0 && jurisdiction && (
              <div className="text-sm text-gray-600">
                Ask me anything about UK discrimination, hate crime, or mental capacity law.
                Type <strong>report</strong> to submit a hate crime report.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i}>
                <Message message={m} />
                {sourcesByMsg[i] && <div className="max-w-3xl mx-auto px-4"><SourcesPanel sources={sourcesByMsg[i]} /></div>}
                {viabilityByMsg[i] && <div className="max-w-3xl mx-auto px-4"><ViabilityCard viability={viabilityByMsg[i]} /></div>}
              </div>
            ))}
            {streaming && <SearchingIndicator />}
            {showReport && <ReportFlow onComplete={(ref) => {
              setShowReport(false);
              setMessages((m) => [...m, { role: "assistant", content: `✅ Report submitted. Reference: **${ref}**. Confirmation email sent.` }]);
            }} />}
          </div>
        </ErrorBoundary>
      </div>
      <Composer
        conversationId={conversationId}
        disabled={streaming || !jurisdiction}
        onSubmit={({ text, images }) => { void send(text, images); }}
      />
    </div>
  );
}
