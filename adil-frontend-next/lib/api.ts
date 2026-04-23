import type {
  V2QueryRequest,
  V2QueryResponse,
  BookSearchResponse,
  V2ExportResponse,
} from "./types";

const PUBLIC_API_URL =
  process.env.NEXT_PUBLIC_RAG_API_URL ||
  "https://rag-api-production-366d.up.railway.app";
const INTERNAL_API_URL =
  process.env.RAG_API_INTERNAL_URL || PUBLIC_API_URL;

function getBaseUrl(): string {
  if (typeof window === "undefined") return INTERNAL_API_URL;
  return PUBLIC_API_URL;
}

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  return res.json();
}

export async function queryV2(
  request: V2QueryRequest,
): Promise<V2QueryResponse> {
  return apiFetch<V2QueryResponse>("/api/v2/query", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export type StreamEvent =
  | { type: "status"; status: string }
  | { type: "text"; text: string }
  | { type: "sources"; sources: import("./types").V2Source[]; usage: Record<string, number> }
  | { type: "error"; error: string };

export async function queryV2Stream(
  request: import("./types").V2QueryRequest,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const url = `${getBaseUrl()}/api/v2/query/stream`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        onEvent(JSON.parse(data));
      } catch {
        // skip malformed events
      }
    }
  }
}

export async function autocompleteBooks(
  q: string,
  limit: number = 20,
): Promise<import("./types").BookAutocompleteResult[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return apiFetch<import("./types").BookAutocompleteResult[]>(`/api/v2/books/autocomplete?${params}`);
}

export async function searchBooks(
  q: string,
  maxResults: number = 50,
): Promise<BookSearchResponse> {
  const params = new URLSearchParams({ q, max_results: String(maxResults) });
  return apiFetch<BookSearchResponse>(`/api/v2/books/search?${params}`);
}

export async function listBooks(
  limit: number = 50,
  offset: number = 0,
): Promise<BookSearchResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<BookSearchResponse>(`/api/v2/books/catalog?${params}`);
}

export async function getExport(
  conversationId: string,
): Promise<V2ExportResponse> {
  return apiFetch<V2ExportResponse>(`/api/v2/export/${conversationId}`);
}

export async function checkHealth(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}

export interface IngestionProgress {
  sources: Record<
    string,
    { active: number; processing: number; failed: number; permanent_failed?: number; total: number }
  >;
  total_books: number;
  total_active: number;
}

export async function getIngestionProgress(): Promise<IngestionProgress> {
  return apiFetch<IngestionProgress>("/api/v2/books/progress");
}

export interface ClientErrorPayload {
  event_type?: "client_stream_error" | "empty_answer" | "frontend_error";
  path?: string;
  detail?: string;
  conversation_id?: string;
  user_tier?: string;
  query_text?: string;
  meta?: Record<string, unknown>;
}

/**
 * Report a client-side error to the rag-api observability pipeline.
 * Never throws — observability must not break the UI.
 */
export async function logClientError(payload: ClientErrorPayload): Promise<void> {
  try {
    const trimmed: ClientErrorPayload = {
      ...payload,
      detail: payload.detail ? payload.detail.slice(0, 1000) : undefined,
      query_text: payload.query_text ? payload.query_text.slice(0, 200) : undefined,
    };
    const url = `${getBaseUrl()}/api/v2/events/client-error`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(trimmed),
      // fire-and-forget; short timeout via AbortController
      signal: AbortSignal.timeout(5000),
    }).catch(() => undefined);
  } catch {
    /* swallow — observability must never break the UI */
  }
}

export { ApiError };
