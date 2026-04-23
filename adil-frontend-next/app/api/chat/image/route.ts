import { ImageQueryRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = ImageQueryRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }
  const upstream = await proxyToBackend(request, "/api/v1/query/image", { body: parsed.data });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
