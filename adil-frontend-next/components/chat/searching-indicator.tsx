"use client";

import { useState, useEffect } from "react";

const TIPS = [
  "Ask Aisha searches across 6,000+ classical Islamic texts",
  "Sources are ranked by relevance to your question",
  "You can filter by specific books using the Book Picker",
  "Arabic and English queries both work",
  "Follow-up questions carry context from earlier in the conversation",
  "Scholar tier gives more technical, source-dense answers",
  "Citations can be exported in Chicago, Harvard, or APA format",
];

interface Props {
  status: string | null;
  bookCount: string;
  filteredCount?: number;
}

export default function SearchingIndicator({ status, bookCount, filteredCount }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [tipIndex, setTipIndex] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    setTipIndex(Math.floor(Math.random() * TIPS.length));
    const rotator = setInterval(() => {
      setTipIndex((i) => (i + 1) % TIPS.length);
    }, 5000);
    return () => clearInterval(rotator);
  }, []);

  const isFiltered = typeof filteredCount === "number" && filteredCount > 0;
  const stageLabel =
    status === "searching"
      ? isFiltered
        ? `Searching ${filteredCount} selected book${filteredCount === 1 ? "" : "s"}`
        : `Searching ${bookCount} books`
      : "Preparing answer";

  // Progress estimate: expect ~35s total (30s retrieval + 5s generation)
  const expectedSeconds = 35;
  const progress = Math.min((elapsed / expectedSeconds) * 100, 95);

  return (
    <div className="flex gap-3 mb-4">
      <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center text-xs font-bold text-white flex-shrink-0 animate-pulse">
        A
      </div>
      <div className="flex-1 space-y-3 pt-1">
        {/* Stage + elapsed */}
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <svg className="animate-spin h-4 w-4 text-brand-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="font-medium">{stageLabel}...</span>
          <span className="text-xs text-gray-400 ml-auto">
            {elapsed}s {elapsed < expectedSeconds && `/ ~${expectedSeconds}s`}
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-brand-400 transition-all duration-1000 ease-linear"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Expectation setting */}
        <p className="text-xs text-gray-500">
          {isFiltered ? (
            <>
              Only your {filteredCount} selected book{filteredCount === 1 ? "" : "s"} will be searched — other books in the library are excluded. Answers typically arrive in 10-20 seconds.
            </>
          ) : (
            <>Classical text search takes 20-40 seconds. The answer will stream in word-by-word once retrieval completes.</>
          )}
        </p>

        {/* Rotating tip */}
        <div className="bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
          <div className="text-[10px] uppercase text-gray-400 font-medium mb-0.5">Did you know</div>
          <p className="text-xs text-gray-600 transition-opacity duration-500" key={tipIndex}>
            {TIPS[tipIndex]}
          </p>
        </div>
      </div>
    </div>
  );
}
