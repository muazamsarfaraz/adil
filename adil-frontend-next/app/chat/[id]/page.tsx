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
        } else if (e.event === "error") {
          const data = e.data as { code?: string; message?: string };
          const msg = data?.message ?? "";
          const isBudget = /monthly spending cap|RESOURCE_EXHAUSTED|429/i.test(msg);
          const isUpstream = /5\d\d|timeout|unavailable/i.test(msg);
          const hint = isBudget
            ? "⏳ **Temporary delay** — Adil is briefly over its usage quota while we top up. The team has been alerted and service usually returns within a few minutes. Please try again shortly."
            : isUpstream
              ? "⏳ A temporary upstream hiccup interrupted the reply. The team has been notified — please try again in a moment."
              : `⚠️ ${msg || "Something went wrong while drafting a reply. Please try again."}`;
          setMessages((m) => {
            const copy = [...m];
            copy[assistantIdx] = { ...copy[assistantIdx], content: hint };
            return copy;
          });
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
          <div className="max-w-3xl mx-auto px-6 md:px-4 py-8 md:py-12">
            {messages.length === 0 && !jurisdiction && (
              <div className="paper-card p-6 md:p-10 relative">
                {/* Opening flourish */}
                <div className="flex items-center gap-3 mb-6">
                  <span
                    className="font-ui text-[11px] uppercase"
                    style={{
                      letterSpacing: "0.28em",
                      color: "var(--color-gold)",
                    }}
                  >
                    ❃ Welcome
                  </span>
                  <div
                    className="flex-1 h-px"
                    style={{
                      background:
                        "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
                      opacity: 0.5,
                    }}
                  />
                </div>

                <h1
                  className="font-display leading-[1.05] mb-4"
                  style={{
                    fontSize: "clamp(28px, 4.5vw, 40px)",
                    fontWeight: 500,
                    color: "var(--color-ink)",
                    letterSpacing: "-0.018em",
                  }}
                >
                  Free, citation-backed UK legal guidance
                  <span
                    className="italic block mt-1"
                    style={{
                      color: "var(--color-emerald)",
                      fontSize: "0.68em",
                      fontWeight: 400,
                    }}
                  >
                    for British Muslims.
                  </span>
                </h1>

                <p
                  className="font-body mb-2"
                  style={{
                    fontSize: 16,
                    lineHeight: 1.7,
                    color: "var(--color-ink-soft)",
                  }}
                >
                  A Muslim Council of Britain initiative covering discrimination, hate
                  crime, and mental capacity &amp; Court of Protection across all four
                  UK jurisdictions. Grounded in UK legislation and{" "}
                  <span
                    className="font-display"
                    style={{ color: "var(--color-gold)", fontWeight: 600 }}
                  >
                    1,000+
                  </span>{" "}
                  court judgments.
                </p>

                <p
                  className="font-ui text-[12px] uppercase mt-6 mb-2"
                  style={{
                    letterSpacing: "0.22em",
                    color: "var(--color-emerald)",
                  }}
                >
                  Select your jurisdiction
                </p>

                <JurisdictionSelector onSelect={setJurisdiction} />
              </div>
            )}
            {messages.length === 0 && jurisdiction && (
              <div className="paper-card p-6 md:p-8">
                <div className="flex items-center gap-3 mb-3">
                  <span
                    className="font-ui text-[11px] uppercase"
                    style={{
                      letterSpacing: "0.24em",
                      color: "var(--color-emerald)",
                    }}
                  >
                    Ready
                  </span>
                  <div
                    className="flex-1 h-px"
                    style={{
                      background:
                        "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
                      opacity: 0.45,
                    }}
                  />
                </div>
                <p
                  className="font-body"
                  style={{
                    fontSize: 16,
                    lineHeight: 1.7,
                    color: "var(--color-ink-soft)",
                  }}
                >
                  Ask about discrimination at work, hate crime, religious leave, or
                  deputyship for an adult with learning disabilities. Type{" "}
                  <strong
                    className="font-display"
                    style={{ color: "var(--color-ink)", fontWeight: 600 }}
                  >
                    report
                  </strong>{" "}
                  to submit a hate-crime report directly.
                </p>
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
            {showReport && <ReportFlow onComplete={(result) => {
              setShowReport(false);
              const ref = result.reference_number ?? null;
              const content = result.dry_run
                ? `🟡 **Dry run only.** The form was filled and the review page was reached, but **no report was submitted** to ${result.target}. The team is in pre-launch testing — please try again once we go live.`
                : ref
                  ? `✅ Report submitted to **${result.target}**. Reference: **${ref}**. A confirmation email has been sent.`
                  : `✅ Report submitted to **${result.target}**. The portal didn't return a reference number — please check your email for confirmation.`;
              setMessages((m) => [...m, { role: "assistant", content }]);
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
