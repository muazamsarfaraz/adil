"use client";

import { presignUpload } from "@/lib/api";
import type { ContentType } from "@/lib/types";

export interface UploadedImage {
  upload_id: string;
  object_key: string;
  preview_url: string;
  name: string;
}

// Backend-accepted MIME types (mirrors lib/types.ts::ContentTypeEnum).
// HEIC/HEIF are NOT in this list because Gemini Vision doesn't accept them
// directly. iOS 11+ transcodes HEIC → JPEG automatically when a user picks a
// photo via `<input type="file">`, so on most iPhones the user never hits the
// HEIC rejection path. Older iOS / camera-raw / Android with HEIC plugins
// will still send raw HEIC — those get a clear error below.
export const ACCEPTED_TYPES: Record<string, ContentType> = {
  "image/png": "image/png",
  "image/jpeg": "image/jpeg",
  "image/webp": "image/webp",
};

export const MAX_BYTES = 10_485_760; // 10 MB
export const MAX_IMAGES_PER_MESSAGE = 5;

// What we put in the `accept` attribute on file inputs. Wider than
// ACCEPTED_TYPES so iOS Camera Roll shows HEIC photos as selectable — iOS
// transcodes them on the way out. The JS layer below catches anything that
// arrives still HEIC-typed and produces a clear error message.
export const FILE_INPUT_ACCEPT = "image/*,.heic,.heif";

export class UploadError extends Error {
  constructor(message: string, public readonly userFacing: string) {
    super(message);
    this.name = "UploadError";
  }
}

function explainUnsupported(file: File): string {
  const t = (file.type || "").toLowerCase();
  if (t === "image/heic" || t === "image/heif" || /\.heic|\.heif/i.test(file.name)) {
    return (
      `${file.name} is an iPhone HEIC photo. ` +
      `Either re-save as JPEG, or change iOS Settings → Camera → Formats → "Most Compatible" and re-take.`
    );
  }
  return `${file.name} (${file.type || "unknown type"}) is not supported. Use PNG, JPEG, or WebP.`;
}

export async function uploadOne(conversationId: string, file: File): Promise<UploadedImage> {
  if (!ACCEPTED_TYPES[file.type]) {
    throw new UploadError(`Unsupported type: ${file.type}`, explainUnsupported(file));
  }
  if (file.size > MAX_BYTES) {
    throw new UploadError(
      `${file.name} is ${(file.size / 1_048_576).toFixed(1)}MB`,
      `${file.name} is larger than 10MB. Please compress or crop and try again.`,
    );
  }

  const presign = await presignUpload({
    conversation_id: conversationId,
    content_type: ACCEPTED_TYPES[file.type],
    size_bytes: file.size,
  });

  const put = await fetch(presign.presigned_url, {
    method: "PUT",
    headers: { "Content-Type": file.type, "Content-Length": String(file.size) },
    body: file,
  });
  if (!put.ok) {
    throw new UploadError(
      `R2 PUT failed: ${put.status}`,
      `Upload failed (HTTP ${put.status}). Please retry. If this keeps happening, check your connection.`,
    );
  }

  return {
    upload_id: presign.upload_id,
    object_key: presign.object_key,
    preview_url: URL.createObjectURL(file),
    name: file.name || `clipboard-${presign.upload_id.slice(0, 8)}.${file.type.split("/")[1] || "img"}`,
  };
}

/**
 * Upload an array of files in sequence, respecting per-message cap.
 * Returns successfully-uploaded images; throws on the FIRST failure with a
 * userFacing message that callers can surface.
 */
export async function uploadMany(
  conversationId: string,
  files: File[],
  remainingSlots: number,
): Promise<UploadedImage[]> {
  const queue = files.slice(0, Math.max(0, remainingSlots));
  const out: UploadedImage[] = [];
  for (const f of queue) {
    out.push(await uploadOne(conversationId, f));
  }
  return out;
}
