"use client";

import { useState } from "react";
import { presignUpload } from "@/lib/api";
import type { ContentType } from "@/lib/types";

export interface UploadedImage {
  upload_id: string;
  object_key: string;
  preview_url: string;
  name: string;
}

const ACCEPTED: Record<string, ContentType> = {
  "image/png": "image/png",
  "image/jpeg": "image/jpeg",
  "image/webp": "image/webp",
};
const MAX_BYTES = 10_485_760;

async function uploadOne(conversationId: string, file: File): Promise<UploadedImage> {
  if (!ACCEPTED[file.type]) throw new Error(`Unsupported type: ${file.type}`);
  if (file.size > MAX_BYTES) throw new Error(`${file.name} is larger than 10MB`);

  const presign = await presignUpload({
    conversation_id: conversationId,
    content_type: ACCEPTED[file.type],
    size_bytes: file.size,
  });

  const put = await fetch(presign.presigned_url, {
    method: "PUT",
    headers: { "Content-Type": file.type, "Content-Length": String(file.size) },
    body: file,
  });
  if (!put.ok) throw new Error(`R2 PUT failed: ${put.status}`);

  return {
    upload_id: presign.upload_id,
    object_key: presign.object_key,
    preview_url: URL.createObjectURL(file),
    name: file.name,
  };
}

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
    const files = Array.from(fileList).slice(0, 5 - images.length);
    setUploading(true);
    try {
      const results: UploadedImage[] = [];
      for (const f of files) {
        results.push(await uploadOne(conversationId, f));
      }
      onChange([...images, ...results]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <label className={`inline-flex items-center gap-2 text-sm cursor-pointer ${uploading ? "opacity-50" : ""}`}>
        <span
          className="px-3 py-1.5 text-[12px] font-ui rounded-full transition-colors"
          style={{
            border: "1px solid rgba(15,62,41,0.25)",
            color: "var(--color-ink-soft)",
          }}
        >
          📎 Attach
        </span>
        <input type="file" multiple accept="image/png,image/jpeg,image/webp"
               className="hidden" disabled={uploading}
               onChange={(e) => handleFiles(e.target.files)} />
      </label>
      {err && <div className="text-[11px] font-ui" style={{ color: "var(--color-rust)" }}>{err}</div>}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {images.map((img) => (
            <div key={img.upload_id} className="relative w-12 h-12">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={img.preview_url} alt={img.name} className="w-full h-full object-cover rounded-xl" />
              <button type="button" onClick={() => onChange(images.filter((i) => i.upload_id !== img.upload_id))}
                      className="absolute -top-2 -right-2 rounded-full w-5 h-5 text-xs flex items-center justify-center"
                      style={{ background: "var(--color-paper)", border: "1px solid rgba(15,62,41,0.25)", color: "var(--color-ink)" }}>
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
