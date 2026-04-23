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

  if (err) return <div className="p-2 text-xs text-red-700">Couldn&apos;t preview: {err}</div>;
  if (!data) return <div className="p-2 text-xs text-gray-500">Previewing {url}…</div>;

  return (
    <div className="p-2 border border-gray-200 rounded bg-gray-50 text-xs">
      <div className="font-semibold">{data.title}</div>
      <div className="text-gray-600 line-clamp-2 mt-1">{data.excerpt}</div>
      <button onClick={onCancel} className="mt-2 text-brand-700 underline">Remove</button>
    </div>
  );
}
