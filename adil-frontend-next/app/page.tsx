"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import SearchInput from "@/components/search-input";
import TierSelector from "@/components/tier-selector";
import BookPicker from "@/components/book-picker";
import type { UserTier } from "@/lib/types";
import { useBookCount } from "@/lib/use-book-count";

const starters = [
  "What is istikharah and how is it performed?",
  "Tafsir of Ayat al-Kursi",
  "What are the pillars of Hajj?",
  "Explain the concept of tawakkul",
];

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [tier, setTier] = useState<UserTier>("layman");
  const [error, setError] = useState<string | null>(null);
  const [bookFilter, setBookFilter] = useState<string[]>([]);
  const bookCount = useBookCount();

  function handleSearch(query: string) {
    setLoading(true);
    setError(null);
    // Generate a conversation ID and redirect immediately — chat page handles streaming
    const conversationId = crypto.randomUUID();
    const saved = localStorage.getItem("user_tier") as UserTier | null;
    const params = new URLSearchParams({
      q: query,
      tier: saved || tier,
    });
    if (bookFilter.length > 0) {
      params.set("books", bookFilter.join(","));
    }
    sessionStorage.setItem(`chat_query_${conversationId}`, query);
    router.push(`/chat/${conversationId}?${params.toString()}`);
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-53px)] px-4">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-semibold text-gray-900 mb-2">
          What would you like to know?
        </h1>
        <p className="text-gray-500 text-sm">
          Search {bookCount} classical Islamic texts
        </p>
      </div>

      <BookPicker selected={bookFilter} onChange={setBookFilter} />

      <SearchInput onSubmit={handleSearch} loading={loading} autoFocus />

      {loading && (
        <div className="mt-4 flex items-center gap-2 text-sm text-gray-500">
          <svg className="animate-spin h-4 w-4 text-brand-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Searching {bookCount} books...
        </div>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      )}

      <div className="flex flex-wrap gap-2 justify-center mt-5 max-w-xl">
        {starters.map((s) => (
          <button
            key={s}
            onClick={() => handleSearch(s)}
            disabled={loading}
            className="px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="mt-6">
        <TierSelector onChange={setTier} />
      </div>
    </div>
  );
}
