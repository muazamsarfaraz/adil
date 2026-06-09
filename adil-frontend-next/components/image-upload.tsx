"use client";

import { useState } from "react";
import {
  FILE_INPUT_ACCEPT,
  MAX_IMAGES_PER_MESSAGE,
  UploadError,
  uploadMany,
  type UploadedImage,
} from "@/lib/uploads";

export type { UploadedImage };

export default function ImageUpload({
  conversationId,
  images,
  onChange,
}: {
  conversationId: string;
  images: UploadedImage[];
  onChange: (next: UploadedImage[]) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList) return;
    setErr(null);
    setUploading(true);
    try {
      const remaining = MAX_IMAGES_PER_MESSAGE - images.length;
      const results = await uploadMany(conversationId, Array.from(fileList), remaining);
      onChange([...images, ...results]);
    } catch (e: unknown) {
      if (e instanceof UploadError) setErr(e.userFacing);
      else setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <label
        className={`inline-flex items-center gap-2 text-sm cursor-pointer ${
          uploading ? "opacity-50" : ""
        }`}
      >
        <span
          className="px-3 py-1.5 text-[12px] font-ui rounded-full transition-colors"
          style={{
            border: "1px solid rgba(15,62,41,0.25)",
            color: "var(--color-ink-soft)",
          }}
        >
          📎 Attach
        </span>
        {/* accept is broad so iOS Camera Roll shows HEIC photos as selectable
            (iOS transcodes to JPEG on selection). Strict MIME allow-check
            happens in lib/uploads.ts::uploadOne. */}
        <input
          type="file"
          multiple
          accept={FILE_INPUT_ACCEPT}
          className="hidden"
          disabled={uploading}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>
      {err && (
        <div
          className="text-[11px] font-ui"
          style={{ color: "var(--color-rust)" }}
          role="alert"
        >
          {err}
        </div>
      )}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {images.map((img) => (
            <div key={img.upload_id} className="relative w-12 h-12">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.preview_url}
                alt={img.name}
                className="w-full h-full object-cover rounded-xl"
              />
              <button
                type="button"
                onClick={() =>
                  onChange(images.filter((i) => i.upload_id !== img.upload_id))
                }
                className="absolute -top-2 -right-2 rounded-full w-5 h-5 text-xs flex items-center justify-center"
                style={{
                  background: "var(--color-paper)",
                  border: "1px solid rgba(15,62,41,0.25)",
                  color: "var(--color-ink)",
                }}
                aria-label={`Remove ${img.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
