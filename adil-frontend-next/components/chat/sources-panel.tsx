"use client";

import { useState } from "react";
import type { Source } from "@/lib/types";
import SourceCard from "./source-card";

export default function SourcesPanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <button onClick={() => setOpen((v) => !v)}
              className="text-xs font-medium text-brand-700 hover:text-brand-900">
        {open ? "Hide" : "Show"} {sources.length} source{sources.length !== 1 ? "s" : ""}
      </button>
      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
          {sources.map((s, i) => (<SourceCard key={i} source={s} />))}
        </div>
      )}
    </div>
  );
}
