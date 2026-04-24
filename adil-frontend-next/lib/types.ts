import { z } from "zod";

export const JurisdictionEnum = z.enum(["england_wales", "scotland", "northern_ireland"]);
export type Jurisdiction = z.infer<typeof JurisdictionEnum>;

export const ContentTypeEnum = z.enum(["image/png", "image/jpeg", "image/webp"]);
export type ContentType = z.infer<typeof ContentTypeEnum>;

// Mirrors backend adil-rag-api/models.py::SourceType
export const SourceTypeEnum = z.enum([
  "statute",
  "case_law",
  "guidance",
  "tribunal_decision",
  "echr_judgment",
]);
export type SourceType = z.infer<typeof SourceTypeEnum>;

export const VentoBandEnum = z.enum(["Lower", "Middle", "Upper", "Exceptional"]);
export type VentoBand = z.infer<typeof VentoBandEnum>;

export const ConversationTurnSchema = z.object({
  // Backend uses Gemini's {user, model} convention; frontend UI uses {user, assistant}
  // and maps at the API boundary. See app/chat/[id]/page.tsx.
  role: z.enum(["user", "model"]),
  content: z.string().max(20_000),
});
export type ConversationTurn = z.infer<typeof ConversationTurnSchema>;

export const QueryRequestSchema = z.object({
  query: z.string().min(1).max(5_000),
  conversation_id: z.string().uuid(),
  conversation_history: z.array(ConversationTurnSchema).max(50).optional(),
  jurisdiction: JurisdictionEnum.optional(),
  max_sources: z.number().int().min(1).max(20).default(10),
  include_viability_score: z.boolean().default(true),
});
export type QueryRequest = z.infer<typeof QueryRequestSchema>;

// Backend emits snake_case Pydantic fields (source_type, neutral_citation, section).
// Accept both shapes and normalise in the UI.
export const SourceSchema = z.object({
  type: SourceTypeEnum.optional(),
  source_type: SourceTypeEnum.optional(),
  title: z.string(),
  url: z.string().url().nullable().optional(),
  citation: z.string().optional(),
  neutral_citation: z.string().nullable().optional(),
  section: z.string().nullable().optional(),
  act_name: z.string().nullable().optional(),
  excerpt: z.string().optional(),
});
export type Source = z.infer<typeof SourceSchema>;

export const ViabilitySchema = z.object({
  score: z.number().int().min(0).max(100),
  vento_band: VentoBandEnum,
  statutory_footing: z.boolean(),
  case_law_precedent: z.boolean(),
  quantum_potential: z.enum(["low", "moderate", "high"]),
  evidence_checklist: z.array(z.string()),
});
export type Viability = z.infer<typeof ViabilitySchema>;

export type StreamEvent =
  | { event: "token"; data: string }
  | { event: "source"; data: Source }
  | { event: "viability"; data: Viability }
  | { event: "done"; data: { conversation_id: string | null; sources_count: number; tokens_used: number } }
  | { event: "error"; data: { message: string; code: string } };

export const ImageQueryRequestSchema = z.object({
  query: z.string().min(1).max(5_000),
  conversation_id: z.string().uuid(),
  upload_ids: z.array(z.string().uuid()).min(1).max(5),
});
export type ImageQueryRequest = z.infer<typeof ImageQueryRequestSchema>;

export const PresignRequestSchema = z.object({
  conversation_id: z.string().uuid(),
  content_type: ContentTypeEnum,
  size_bytes: z.number().int().min(1).max(10_485_760),
});
export type PresignRequest = z.infer<typeof PresignRequestSchema>;

export const PresignResponseSchema = z.object({
  upload_id: z.string().uuid(),
  presigned_url: z.string().url(),
  object_key: z.string(),
  expires_at: z.string(),
});
export type PresignResponse = z.infer<typeof PresignResponseSchema>;

export const ReporterInfoSchema = z.object({
  name: z.string().min(1).max(200),
  email: z.string().email().max(200),
  phone: z.string().max(50).optional(),
  dob: z.string().optional(),
  address: z.string().max(500).optional(),
});

export const IncidentInfoSchema = z.object({
  target_org: z.string().min(1).max(50),
  summary: z.string().min(10).max(5_000),
  date: z.string().optional(),
  location: z.string().max(500).optional(),
});

export const ReportSubmitRequestSchema = z.object({
  reporter: ReporterInfoSchema,
  incident: IncidentInfoSchema,
  turnstile_token: z.string().min(10),
});
export type ReportSubmitRequest = z.infer<typeof ReportSubmitRequestSchema>;

export const ExtractUrlRequestSchema = z.object({
  url: z.string().url().max(2_000),
});
export type ExtractUrlRequest = z.infer<typeof ExtractUrlRequestSchema>;
