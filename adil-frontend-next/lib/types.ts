export interface V2Source {
  book_id: string;
  title: string;
  author_name: string | null;
  author_death_year: number | null;
  excerpt: string;
  source_type: string;
  usul_slug: string | null;
  url: string | null;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface V2QueryRequest {
  query: string;
  user_tier?: "scholar" | "student" | "layman";
  max_sources?: number;
  include_export?: boolean;
  book_ids?: string[];
  synthesis?: boolean;
  conversation_id?: string;
}

export interface V2QueryResponse {
  conversation_id: string;
  intent: string;
  answer: string;
  sources: V2Source[];
  sources_count: number;
  no_results_reason: string | null;
  user_tier: string;
  export_available: boolean;
  usage: TokenUsage | null;
}

export interface BookSearchResult {
  slug: string;
  title_ar: string | null;
  title_en: string | null;
  author_name_ar: string | null;
  author_name_en: string | null;
  author_death_year: number | null;
  genres: string[];
  url: string | null;
}

export interface BookSearchResponse {
  query: string;
  results: BookSearchResult[];
  total: number;
}

export interface V2ExportResponse {
  id: string;
  conversation_id: string;
  question: string;
  response: string;
  sources: V2Source[];
  user_tier: string;
  created_at: string | null;
  disclaimer: string;
}

export type UserTier = "scholar" | "student" | "layman";

export type CitationStyle = "chicago" | "harvard" | "apa";

export interface HadithGrading {
  scholar: string;
  hukm: "sahih" | "hasan" | "daif" | "mawdu" | "unknown";
  source_book: string;
  notes?: string;
}

export interface BookAutocompleteResult {
  book_id: string;
  title: string;
  title_ar: string | null;
  author: string | null;
  author_ar: string | null;
}

export interface BookCollection {
  id: string;
  name: string;
  name_ar?: string;
  book_ids: string[];
}
