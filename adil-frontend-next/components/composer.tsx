"use client";

import { useState, type FormEvent } from "react";
import ImageUpload, { type UploadedImage } from "./image-upload";
import UrlPreview from "./url-preview";

interface Props {
  conversationId: string;
  disabled: boolean;
  onSubmit: (payload: { text: string; images: UploadedImage[]; url?: string }) => void;
}

const URL_RE = /(https?:\/\/\S+)/i;

export default function Composer({ conversationId, disabled, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [pastedUrl, setPastedUrl] = useState<string | null>(null);

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    const match = pasted.match(URL_RE);
    if (match && !pastedUrl) setPastedUrl(match[0]);
  };

  const submit = (e: FormEvent | React.KeyboardEvent) => {
    e.preventDefault();
    if (!text.trim() && images.length === 0) return;
    onSubmit({ text: text.trim(), images, url: pastedUrl ?? undefined });
    setText("");
    setImages([]);
    setPastedUrl(null);
  };

  return (
    <form
      onSubmit={submit}
      className="relative border-t px-4 py-5 md:py-6"
      style={{
        borderColor: "rgba(15,62,41,0.18)",
        background:
          "linear-gradient(to top, rgba(235,226,201,0.6) 0%, rgba(244,238,220,0.2) 100%)",
      }}
    >
      {/* gold hairline */}
      <div
        aria-hidden
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(to right, transparent 0%, var(--color-gold) 30%, var(--color-gold) 70%, transparent 100%)",
          opacity: 0.35,
        }}
      />
      <div className="max-w-3xl mx-auto flex flex-col gap-3">
        {pastedUrl && <UrlPreview url={pastedUrl} onCancel={() => setPastedUrl(null)} />}
        <div
          className="paper-card flex items-center gap-3 px-4 py-3"
          style={{ background: "var(--color-paper)", borderRadius: 999 }}
        >
          <ImageUpload conversationId={conversationId} images={images} onChange={setImages} />
          <textarea
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={handlePaste}
            placeholder="Ask about discrimination, hate crime, deputyship, or Court of Protection…"
            disabled={disabled}
            className="flex-1 min-h-10 max-h-40 p-2 bg-transparent border-0 resize-none outline-none font-body"
            style={{
              color: "var(--color-ink)",
              fontSize: 16,
              lineHeight: 1.6,
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { submit(e); } }}
          />
          <button
            type="submit"
            disabled={disabled}
            aria-label="Send"
            className="flex items-center justify-center transition-all shrink-0"
            style={{
              width: 40,
              height: 40,
              borderRadius: 999,
              background: disabled ? "rgba(15,62,41,0.2)" : "var(--color-ink)",
              color: disabled ? "rgba(244,238,220,0.6)" : "var(--color-paper)",
              border: `1px solid ${disabled ? "rgba(15,62,41,0.2)" : "var(--color-ink)"}`,
              cursor: disabled ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => {
              if (!disabled) {
                e.currentTarget.style.background = "var(--color-emerald)";
                e.currentTarget.style.borderColor = "var(--color-emerald)";
              }
            }}
            onMouseLeave={(e) => {
              if (!disabled) {
                e.currentTarget.style.background = "var(--color-ink)";
                e.currentTarget.style.borderColor = "var(--color-ink)";
              }
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 2 L8 14 M3 7 L8 2 L13 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <p
          className="font-ui text-[11px] text-center"
          style={{
            color: "var(--color-ink-faded)",
            letterSpacing: "0.02em",
          }}
        >
          <span style={{ color: "var(--color-gold)" }}>❃</span>{" "}
          AskAdil is an educational tool, not a law firm. Always consult a qualified solicitor before taking action.
        </p>
      </div>
    </form>
  );
}
