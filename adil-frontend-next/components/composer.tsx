"use client";

import { useState, type FormEvent } from "react";
import ImageUpload, { type UploadedImage } from "./image-upload";
import UrlPreview from "./url-preview";
import { MAX_IMAGES_PER_MESSAGE, UploadError, uploadMany } from "@/lib/uploads";

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
  const [pasteUploading, setPasteUploading] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);

  /**
   * Handles BOTH paths in one event:
   *   1. Text paste (existing) — scan for a URL to surface as a preview card.
   *   2. Image paste (new) — pull any image File items out of clipboardData and
   *      upload them via the same R2 presign flow ImageUpload uses. Triggered by
   *      screenshots (Cmd/Ctrl+V after Cmd/Win+Shift+S), copied images from a
   *      browser, or images copied from Photos / Finder / Files.
   */
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    // Path 1 — text → URL detection (unchanged)
    const pastedText = e.clipboardData.getData("text");
    const urlMatch = pastedText.match(URL_RE);
    if (urlMatch && !pastedUrl) setPastedUrl(urlMatch[0]);

    // Path 2 — image files from the clipboard
    const items = Array.from(e.clipboardData.items ?? []);
    const imageFiles: File[] = [];
    for (const item of items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const f = item.getAsFile();
        if (f) imageFiles.push(f);
      }
    }
    if (imageFiles.length === 0) return;

    // Stop the textarea inserting binary garbage as text.
    e.preventDefault();
    setPasteError(null);
    setPasteUploading(true);
    try {
      const remaining = MAX_IMAGES_PER_MESSAGE - images.length;
      if (remaining <= 0) {
        setPasteError(`You can attach up to ${MAX_IMAGES_PER_MESSAGE} images per message.`);
        return;
      }
      const uploaded = await uploadMany(conversationId, imageFiles, remaining);
      setImages([...images, ...uploaded]);
    } catch (err: unknown) {
      if (err instanceof UploadError) setPasteError(err.userFacing);
      else setPasteError(err instanceof Error ? err.message : "Pasted image upload failed");
    } finally {
      setPasteUploading(false);
    }
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
        {pasteUploading && (
          <div
            className="text-[12px] font-ui px-3"
            style={{ color: "var(--color-ink-soft)" }}
            aria-live="polite"
          >
            Uploading pasted image…
          </div>
        )}
        {pasteError && (
          <div
            className="text-[12px] font-ui px-3 flex items-center gap-2"
            style={{ color: "var(--color-rust)" }}
            role="alert"
          >
            <span>{pasteError}</span>
            <button
              type="button"
              onClick={() => setPasteError(null)}
              className="underline opacity-70 hover:opacity-100"
              aria-label="Dismiss error"
            >
              dismiss
            </button>
          </div>
        )}
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
            placeholder="Ask about discrimination, hate crime, or deputyship — attach a photo or paste a link…"
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
        <p
          className="font-ui text-[10px] text-center"
          style={{
            color: "var(--color-ink-faded)",
            opacity: 0.55,
            letterSpacing: "0.04em",
            marginTop: 4,
          }}
          // Build stamp: surfaced in the UI so anyone can verify which deploy
          // they're looking at. Auto-bumps on every Railway deploy via
          // RAILWAY_GIT_COMMIT_SHA injected in next.config.ts.
          aria-label="Build version"
        >
          v{process.env.NEXT_PUBLIC_BUILD_DATE} · {process.env.NEXT_PUBLIC_BUILD_SHA}
        </p>
      </div>
    </form>
  );
}
