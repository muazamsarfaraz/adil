import { extractClientIp } from "./client-ip";

export interface ProxyOptions {
  method?: "GET" | "POST";
  body?: unknown;
  extraHeaders?: Record<string, string>;
}

export function getRagApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_RAG_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_RAG_API_URL is not configured");
  return url.replace(/\/+$/, "");
}

export function getRagApiKey(): string {
  const key = process.env.RAG_API_KEY;
  if (!key) throw new Error("RAG_API_KEY is not configured (server-side secret)");
  return key;
}

export async function proxyToBackend(
  request: Request,
  path: string,
  options: ProxyOptions = {},
): Promise<Response> {
  const baseUrl = getRagApiBaseUrl();
  const apiKey = getRagApiKey();
  const clientIp = extractClientIp(request);

  const headers: Record<string, string> = {
    "X-API-Key": apiKey,
    "X-AskAdil-Client-IP": clientIp,
    "Content-Type": "application/json",
    ...(options.extraHeaders ?? {}),
  };

  return fetch(`${baseUrl}${path}`, {
    method: options.method ?? "POST",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
}
