import { QueryRequestSchema } from "@/lib/types";
import { getRagApiBaseUrl, getRagApiKey } from "@/lib/proxy";
import { extractClientIp } from "@/lib/client-ip";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = QueryRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const upstream = await fetch(`${getRagApiBaseUrl()}/api/v1/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getRagApiKey(),
      "X-AskAdil-Client-IP": extractClientIp(request),
      Accept: "text/event-stream",
    },
    body: JSON.stringify(parsed.data),
  });

  const contentType = upstream.headers.get("content-type") ?? "text/event-stream";
  const headers: Record<string, string> = {
    "Content-Type": contentType,
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
  };
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers["Retry-After"] = retryAfter;

  return new Response(upstream.body, { status: upstream.status, headers });
}
