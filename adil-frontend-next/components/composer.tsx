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
    <form onSubmit={submit} className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto flex flex-col gap-2">
        {pastedUrl && <UrlPreview url={pastedUrl} onCancel={() => setPastedUrl(null)} />}
        <div className="flex items-end gap-2">
          <ImageUpload conversationId={conversationId} images={images} onChange={setImages} />
          <textarea
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={handlePaste}
            placeholder="Type your question…"
            disabled={disabled}
            className="flex-1 min-h-10 max-h-40 p-2 border border-gray-300 rounded text-sm focus:outline-none focus:border-brand-500"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { submit(e); } }}
          />
          <button type="submit" disabled={disabled}
                  className="px-4 py-2 bg-brand-900 text-white rounded hover:bg-brand-700 disabled:opacity-50">
            ↑
          </button>
        </div>
      </div>
    </form>
  );
}
