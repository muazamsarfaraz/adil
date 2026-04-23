"use client";

import { useState } from "react";
import type { Source } from "@/lib/types";
import SourceCard from "./source-card";

export default function SourcesPanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;

  return (
    <div className="mt-6 max-w-3xl mx-auto">
      {/* Trigger row — typographic, not a rectangle button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 group py-2"
        aria-expanded={open}
      >
        <span
          className="font-ui text-[11px] uppercase whitespace-nowrap"
          style={{
            letterSpacing: "0.22em",
            color: "var(--color-emerald)",
          }}
        >
          {open ? "Hide" : "Show"} {sources.length} cited source{sources.length !== 1 ? "s" : ""}
        </span>
        <div
          className="flex-1 h-px"
          style={{
            background:
              "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
            opacity: 0.5,
          }}
        />
        <span
          className="font-display text-[color:var(--color-gold)] transition-transform"
          style={{
            fontSize: 14,
            transform: open ? "rotate(90deg)" : "rotate(0deg)",
            display: "inline-block",
          }}
          aria-hidden
        >
          ▸
        </span>
      </button>

      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
          {sources.map((s, i) => (
            <SourceCard key={i} source={s} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
