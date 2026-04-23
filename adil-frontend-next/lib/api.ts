"use client";

import type {
  ImageQueryRequest, PresignRequest, PresignResponse,
  ReportSubmitRequest, ExtractUrlRequest,
} from "./types";

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw Object.assign(new Error(text || resp.statusText), { status: resp.status });
  }
  return (await resp.json()) as T;
}

export async function presignUpload(body: PresignRequest): Promise<PresignResponse> {
  const resp = await fetch("/api/upload/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<PresignResponse>(resp);
}

export async function submitReport(body: ReportSubmitRequest): Promise<{ reference: string }> {
  const resp = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<{ reference: string }>(resp);
}

export async function extractUrl(body: ExtractUrlRequest): Promise<{ title: string; excerpt: string }> {
  const resp = await fetch("/api/extract-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json(resp);
}

export async function queryImage(body: ImageQueryRequest): Promise<unknown> {
  const resp = await fetch("/api/chat/image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json(resp);
}
