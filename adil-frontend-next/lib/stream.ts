"use client";

import { fetchEventSource, EventSourceMessage } from "@microsoft/fetch-event-source";
import type { StreamEvent } from "./types";

export interface StreamOptions {
  url: string;
  body: unknown;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
  onError: (err: { message: string; status?: number; retryAfter?: number }) => void;
  maxAttempts?: number;
}

export async function streamChat(opts: StreamOptions): Promise<void> {
  const maxAttempts = opts.maxAttempts ?? 1;
  let attempt = 0;

  while (attempt < maxAttempts) {
    attempt += 1;
    let retry = false;

    try {
      await fetchEventSource(opts.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(opts.body),
        signal: opts.signal,
        openWhenHidden: true,

        async onopen(response) {
          if (response.ok && response.headers.get("content-type")?.startsWith("text/event-stream")) return;
          if (response.status === 429) {
            const retryAfter = parseInt(response.headers.get("retry-after") ?? "0", 10);
            opts.onError({ message: "Too many requests", status: 429, retryAfter: retryAfter || undefined });
            throw new Error("429");
          }
          if (response.status >= 400 && response.status < 500) {
            const text = await response.text().catch(() => "");
            opts.onError({ message: text || response.statusText, status: response.status });
            throw new Error(`client-${response.status}`);
          }
          retry = true;
          throw new Error(`server-${response.status}`);
        },

        onmessage(msg: EventSourceMessage) {
          if (!msg.event || !msg.data) return;
          try {
            const parsed: StreamEvent = {
              event: msg.event as StreamEvent["event"],
              data: JSON.parse(msg.data),
            } as StreamEvent;
            opts.onEvent(parsed);
          } catch {
            /* malformed chunk — skip */
          }
        },

        onerror(err) {
          retry = true;
          throw err;
        },

        onclose() { retry = false; },
      });
      return;
    } catch {
      if (!retry || attempt >= maxAttempts) {
        if (!retry) return;
        opts.onError({ message: "Connection failed after retries" });
        return;
      }
      const base = 500;
      const delay = Math.min(base * 2 ** (attempt - 1), 30_000) + Math.random() * 1000;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}
