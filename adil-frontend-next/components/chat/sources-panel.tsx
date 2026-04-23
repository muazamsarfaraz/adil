"use client";

import { useState } from "react";
import type { V2Source, CitationStyle } from "@/lib/types";
import SourceCard from "./source-card";
import { formatCitation } from "@/lib/citations";

interface SourcesPanelProps {
  sources: V2Source[];
  highlightedIndex: number | null;
}

export default function SourcesPanel({ sources, highlightedIndex }: SourcesPanelProps) {
  const [view, setView] = useState<"cards" | "bibliography">("cards");
  const [style, setStyle] = useState<CitationStyle>("chicago");

  if (sources.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-400 text-center">No sources found</div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200">
        <span className="text-sm font-medium text-gray-700">Sources ({sources.length})</span>
        <div className="flex gap-1">
          <button
            onClick={() => setView("cards")}
            className={`px-2 py-0.5 rounded text-xs ${
              view === "cards" ? "bg-gray-200 text-gray-800" : "text-gray-400 hover:text-gray-600"
            }`}
          >
            Cards
          </button>
          <button
            onClick={() => setView("bibliography")}
            className={`px-2 py-0.5 rounded text-xs ${
              view === "bibliography" ? "bg-gray-200 text-gray-800" : "text-gray-400 hover:text-gray-600"
            }`}
          >
            Bibliography
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {view === "cards" ? (
          sources.map((s, i) => (
            <SourceCard key={`${s.book_id}-${i}`} index={i + 1} source={s} highlighted={highlightedIndex === i + 1} />
          ))
        ) : (
          <>
            <div className="flex items-center gap-2 mb-2">
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value as CitationStyle)}
                className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
              >
                <option value="chicago">Chicago</option>
                <option value="harvard">Harvard</option>
                <option value="apa">APA</option>
              </select>
              <button
                onClick={() => {
                  const all = sources.map((s) => formatCitation(s, style)).join("\n\n");
                  navigator.clipboard.writeText(all);
                }}
                className="text-xs text-brand-500 hover:text-brand-600"
              >
                Copy all
              </button>
            </div>
            {sources.map((s, i) => (
              <div key={`${s.book_id}-${i}`} className="text-xs text-gray-700 mb-2 flex gap-2">
                <span className="text-gray-400 flex-shrink-0">[{i + 1}]</span>
                <div>
                  <p>{formatCitation(s, style)}</p>
                  <button
                    onClick={() => navigator.clipboard.writeText(formatCitation(s, style))}
                    className="text-[10px] text-gray-400 hover:text-brand-500 mt-0.5"
                  >
                    Copy
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
