import { ReportSubmitRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";
import { verifyTurnstile } from "@/lib/turnstile";
import { extractClientIp } from "@/lib/client-ip";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = ReportSubmitRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const clientIp = extractClientIp(request);
  const ts = await verifyTurnstile(parsed.data.turnstile_token, clientIp);
  if (!ts.success) {
    return Response.json({ error: "turnstile_failed", codes: ts.errorCodes ?? [] }, { status: 403 });
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { turnstile_token, ...forwardBody } = parsed.data;
  const upstream = await proxyToBackend(request, "/api/v1/submit-report", { body: forwardBody });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
