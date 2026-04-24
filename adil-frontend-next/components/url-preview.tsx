"use client";

import { useEffect, useState } from "react";
import { extractUrl } from "@/lib/api";

export default function UrlPreview({ url, onCancel }: { url: string; onCancel: () => void }) {
  const [data, setData] = useState<{ title: string; excerpt: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    extractUrl({ url })
      .then((d) => !cancelled && setData(d as { title: string; excerpt: string }))
      .catch((e) => !cancelled && setErr(e.message || "Extraction failed"));
    return () => { cancelled = true; };
  }, [url]);

  if (err)
    return (
      <div className="px-3 py-2 rounded-2xl font-ui text-[11px]" style={{ color: "var(--color-rust)" }}>
        Couldn&apos;t preview: {err}
      </div>
    );
  if (!data)
    return (
      <div className="px-3 py-2 rounded-2xl font-ui text-[11px]" style={{ color: "var(--color-ink-faded)" }}>
        Previewing {url}…
      </div>
    );

  return (
    <div
      className="px-4 py-3 rounded-2xl font-body text-[13px]"
      style={{
        border: "1px solid rgba(15,62,41,0.15)",
        background: "rgba(255,255,255,0.35)",
      }}
    >
      <div className="font-display font-semibold" style={{ color: "var(--color-ink)" }}>{data.title}</div>
      <div className="line-clamp-2 mt-1 italic" style={{ color: "var(--color-ink-faded)" }}>{data.excerpt}</div>
      <button
        onClick={onCancel}
        className="mt-2 font-ui text-[10px] uppercase"
        style={{ letterSpacing: "0.2em", color: "var(--color-emerald)" }}
      >
        Remove
      </button>
    </div>
  );
}
